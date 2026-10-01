# -*- coding: utf-8 -*-
"""Stufe 4 der Ansicht KONSOLE - was davon geblieben ist: die Konsolensuche.

Stufe 4 brachte am 22.09.2026 Remote Play (Chiaki, Kopplung mit
ActRemoteLink) und ProsperoLight. Am 25.09.2026 wurde beides auf Wunsch des
Nutzers wieder aus dem Programm genommen ("Diese zwei Knoepfe bitte wieder
entfernen. Diese moechte ich nicht mehr im Programm"). Geblieben ist die
Suche ueber das Discovery-Protokoll von Remote Play (UDP 9302): Die
Uebersicht der Ansicht KONSOLE braucht sie, weil sie als einzige Messung
auch eine Konsole im Ruhemodus erkennt.

Gemessen wird gegen eine **echte** Gegenstelle auf diesem Rechner: einen
UDP-Horcher, der wie eine PS5 auf ``SRCH`` antwortet (einmal eingeschaltet,
einmal im Ruhemodus).
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pruefumgebung                                          # noqa: E402
pruefumgebung.umlenken("konsole_suche")

import PS5ImageConverter_Pro_FINAL_revised as APP             # noqa: E402
from ps5_validator.utils import payload_versand               # noqa: E402
from ps5_validator.utils import remoteplay as rp              # noqa: E402
from ps5_validator.utils.i18n import STRINGS                  # noqa: E402

PROJEKT = Path(__file__).resolve().parent


class _SuchStube:
    """Antwortet auf UDP wie eine Konsole auf ``SRCH``."""

    def __init__(self, status: int = 200) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.status = int(status)
        self.laeuft = True
        self.gefragt = 0
        self.faden = threading.Thread(target=self._bedienen, daemon=True,
                                      name="such-stube")
        self.faden.start()

    def _bedienen(self) -> None:
        self.sock.settimeout(0.3)
        while self.laeuft:
            try:
                daten, absender = self.sock.recvfrom(2048)
            except (socket.timeout, OSError):
                continue
            if not daten.startswith(b"SRCH"):
                continue
            self.gefragt += 1
            antwort = ("HTTP/1.1 %d %s\n"
                       "host-id:1122334455667788\n"
                       "host-type:PS5\n"
                       "host-name:Wohnzimmer\n"
                       "system-version:12000000\n"
                       % (self.status, "Ok" if self.status == 200 else "Standby"))
            try:
                self.sock.sendto(antwort.encode("utf-8"), absender)
            except OSError:
                return

    def schliessen(self) -> None:
        self.laeuft = False
        try:
            self.sock.close()
        except OSError:
            pass


def _freier_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class SucheTests(unittest.TestCase):

    def test_eingeschaltete_konsole_wird_gefunden(self):
        stube = _SuchStube(status=200)
        try:
            treffer = rp.suchen("127.0.0.1", zeit=1.5, port=stube.port)
        finally:
            stube.schliessen()
        self.assertEqual(1, len(treffer))
        konsole = treffer[0]
        self.assertTrue(konsole.bereit)
        self.assertFalse(konsole.standby)
        self.assertEqual("Wohnzimmer", konsole.name)
        self.assertEqual("PS5", konsole.art)
        self.assertEqual("12000000", konsole.firmware)
        self.assertEqual("remoteplay.status_an", konsole.status_schluessel)

    def test_ruhemodus_wird_als_solcher_erkannt(self):
        """620 ist der Fall, den ein TCP-Portscan gar nicht sieht."""
        stube = _SuchStube(status=620)
        try:
            treffer = rp.suchen("127.0.0.1", zeit=1.5, port=stube.port)
        finally:
            stube.schliessen()
        self.assertEqual(1, len(treffer))
        self.assertTrue(treffer[0].standby)
        self.assertFalse(treffer[0].bereit)
        self.assertEqual("remoteplay.status_standby",
                         treffer[0].status_schluessel)

    def test_ohne_antwort_leere_liste(self):
        treffer = rp.suchen("127.0.0.1", zeit=0.6, port=_freier_port())
        self.assertEqual([], treffer)

    def test_ports_sind_die_bekannten(self):
        self.assertEqual(9302, rp.PS5_SUCHPORT)
        self.assertEqual(987, rp.PS4_SUCHPORT)


class TexteTests(unittest.TestCase):

    def test_jeder_zustand_der_suche_hat_seinen_text(self):
        for status in (200, 620, 0):
            konsole = rp.Konsole(adresse="10.0.0.5", status=status)
            for sprache in ("de", "en"):
                with self.subTest(status=status, sprache=sprache):
                    self.assertTrue(STRINGS[konsole.status_schluessel].get(sprache))

    def test_nur_die_zustaende_der_suche_sind_geblieben(self):
        self.assertEqual({"remoteplay.status_an", "remoteplay.status_standby",
                          "remoteplay.status_unklar"},
                         {k for k in STRINGS if k.startswith("remoteplay.")})


class EntferntTests(unittest.TestCase):
    """Remote Play und ProsperoLight sind heraus (Nutzerwunsch vom 25.09.2026).

    Festgehalten wie beim Entfernen von "Spiel holen" und "Zurueckspielen"
    (test_bibliothek_seite): Kommt etwas davon zurueck, faellt es hier auf.
    """

    def test_drei_knoepfe_und_jeder_ist_verdrahtet(self):
        klasse = APP.PS5ConverterGUI
        self.assertEqual(["dienste", "spielstaende", "bibliothek", "prosperomgr"],
                         [k for _s, k in klasse._KONSOLE_KNOEPFE])
        for _schluessel, kennung in klasse._KONSOLE_KNOEPFE:
            with self.subTest(kennung=kennung):
                methode = (klasse._KONSOLE_FENSTER.get(kennung, "")
                           or klasse._KONSOLE_SEITEN.get(kennung, "")
                           or klasse._KONSOLE_AKTIONEN.get(kennung, ""))
                self.assertTrue(methode, "Kennung %s ohne Fenster" % kennung)
                self.assertTrue(callable(getattr(klasse, methode, None)))
        fenster, seiten, aktionen = (set(klasse._KONSOLE_FENSTER),
                                    set(klasse._KONSOLE_SEITEN),
                                    set(klasse._KONSOLE_AKTIONEN))
        self.assertFalse(fenster & seiten, "Eine Kennung steht in mehr als einer Gruppe.")
        self.assertFalse(fenster & aktionen, "Eine Kennung steht in mehr als einer Gruppe.")
        self.assertFalse(seiten & aktionen, "Eine Kennung steht in mehr als einer Gruppe.")

    def test_keine_methode_bleibt_zurueck(self):
        klasse = APP.PS5ConverterGUI
        uebrig = sorted(n for n in dir(klasse) if n.startswith((
            "_rpassist", "_rpspiel", "_remoteplay", "_chiaki", "_streaming",
            "_STREAMING", "_ACTREMOTELINK", "_actremotelink", "_show_konsole_remoteplay",
            "_show_konsole_prosperolight", "_konsole_remoteplay", "_konsole_assistent")))
        self.assertEqual([], uebrig)

    def test_keine_module_und_keine_texte(self):
        for modul in ("remoteplay_agent", "chiaki_einrichten"):
            with self.subTest(modul=modul):
                self.assertIsNone(importlib.util.find_spec("ps5_validator.utils." + modul))
        self.assertFalse([n for n in dir(rp) if n.startswith(("chiaki", "sunshine", "Chiaki",
                                                               "Sunshine"))])
        self.assertFalse(hasattr(payload_versand, "Mitleser"))
        praefixe = ("rpassist.", "rpspiel.", "chiaki.", "prospero.")
        self.assertEqual([], sorted(k for k in STRINGS if k.startswith(praefixe)
                                    or k in ("konsole.btn_remoteplay",
                                             "konsole.btn_prosperolight",
                                             "konsole.btn_actremotelink")))

    def test_kein_ordner_streaming_mehr_im_bau(self):
        self.assertFalse((PROJEKT / "Streaming" / "README.md").exists())
        skript = (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('foreach ($_ordner in @("libs"))', skript)


if __name__ == "__main__":
    unittest.main()
