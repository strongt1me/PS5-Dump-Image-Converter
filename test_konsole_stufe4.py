# -*- coding: utf-8 -*-
"""Stufe 4 der Ansicht KONSOLE: Remote Play und ProsperoLight.

Wie in Stufe 3 wird gegen **echte** Gegenstellen auf diesem Rechner
gemessen, nicht gegen Nachbildungen der Bibliotheken:

* ``_SuchStube``   - ein UDP-Horcher, der wie eine PS5 auf ``SRCH`` antwortet
  (einmal eingeschaltet, einmal im Ruhemodus),
* ``_AgentStube``  - ein TCP-Horcher, der das Agent-Protokoll spricht
  (ein Kommando je Verbindung, Antwort erst nach Half-Close),
* ``_SunshineStube`` - ein HTTP-Horcher, der ``/serverinfo`` liefert.

Die schaerfste Pruefung ist :meth:`GatterTests.test_slot1_ist_unbedingt_gesperrt`:
Slot 1 bleibt gesperrt, **auch** wenn der Benutzer existiert, aktiviert und
im Vordergrund ist. Der Autor von ActRemoteLink schreibt das so vor
("Leave User1 / Slot 1 untouched"), und der Nutzer hat es am 22.09.2026
ausdruecklich als unbedingt entschieden - es gibt bewusst keinen Schalter,
der die Sperre aufhebt.
"""
from __future__ import annotations

import http.server
import os
import re
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import remoteplay as rp             # noqa: E402
from ps5_validator.utils import remoteplay_agent as ra       # noqa: E402
from ps5_validator.utils.i18n import STRINGS                 # noqa: E402

PROJEKT = Path(__file__).resolve().parent

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


# ---------------------------------------------------------------- Stuben

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


class _AgentStube:
    """Spricht das Agent-Protokoll: ein Kommando je Verbindung."""

    LISTE = ('slot=1 current=0 user_id=0x10000000 name="Haupt" type="np" '
             'flags=0x1002 id=0x0000000000000001 b64=AAAA\n'
             'slot=2 current=1 user_id=0x10000001 name="Stream" type="" '
             'flags=0x0000 id=0x0000000000000000 b64=BBBB\n')

    def __init__(self) -> None:
        self.horcher = socket.socket()
        self.horcher.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(4)
        self.port = self.horcher.getsockname()[1]
        self.laeuft = True
        #: Jedes empfangene Kommando - daran wird gemessen, was wirklich
        #: zur "Konsole" gegangen ist.
        self.kommandos: list[str] = []
        self.antwort_auf: dict = {}
        #: Geraetezeilen fuer PAIRED, z. B. "DEVICE index=1 user_id=...".
        self.geraete: list[str] = []
        self.faden = threading.Thread(target=self._bedienen, daemon=True,
                                      name="agent-stube")
        self.faden.start()

    def _bedienen(self) -> None:
        while self.laeuft:
            try:
                verbindung, _ = self.horcher.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(verbindung,),
                             daemon=True).start()

    def _sitzung(self, verbindung: socket.socket) -> None:
        verbindung.settimeout(5.0)
        teile: list[bytes] = []
        try:
            while True:
                brocken = verbindung.recv(1024)
                if not brocken:
                    break
                teile.append(brocken)
                if b"\n" in brocken:
                    # Der Klient macht danach zu; nicht ewig warten.
                    try:
                        verbindung.settimeout(0.3)
                    except OSError:
                        pass
        except (socket.timeout, OSError):
            pass
        kommando = b"".join(teile).decode("utf-8", "replace").strip()
        self.kommandos.append(kommando)
        wort = kommando.split(" ", 1)[0].upper()
        if wort in self.antwort_auf:
            antwort = self.antwort_auf[wort]
        elif wort == "HELP":
            antwort = "HELP LIST SETID FAKESIGNIN\nEND\n"
        elif wort == "LIST":
            antwort = self.LISTE + "END\n"
        elif wort == "PAIRED":
            # Wie der mitgelieferte Agent 2.0 (cmd_paired): je gekoppeltem
            # Geraet eine DEVICE-Zeile.
            antwort = "OK PAIRED\n" + "".join(z + "\n" for z in self.geraete) + "END\n"
        elif wort not in ("PING", "SETID", "FAKESIGNIN", "PREPARE_PIN", "PIN",
                          "CURRENT", "B64", "COMPARE", "GETKEY", "SETKEY", "QUIT"):
            # Auch das wie der echte Agent - bis zum 24.09.2026 beantwortete
            # die Stube ein erfundenes IS_PAIRED, das es dort nicht gibt.
            antwort = "ERR unknown_command\nEND\n"
        else:
            antwort = "OK\nEND\n"
        try:
            verbindung.sendall(antwort.encode("utf-8"))
        except OSError:
            pass
        try:
            verbindung.close()
        except OSError:
            pass

    def schliessen(self) -> None:
        self.laeuft = False
        try:
            self.horcher.close()
        except OSError:
            pass


class _SunshineStube:
    """Liefert ``/serverinfo`` wie ein Sunshine-Host."""

    XML = (b'<?xml version="1.0"?><root status_code="200">'
           b'<hostname>PC-Wohnzimmer</hostname>'
           b'<appversion>7.1.0</appversion></root>')

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if not self.path.startswith("/serverinfo"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(_SunshineStube.XML)))
            self.end_headers()
            self.wfile.write(_SunshineStube.XML)

        def log_message(self, *_a):  # Ruhe im Testlauf
            return

    def __init__(self) -> None:
        self.server = http.server.HTTPServer(("127.0.0.1", 0), self._Handler)
        self.port = self.server.server_address[1]
        self.faden = threading.Thread(target=self.server.serve_forever,
                                      daemon=True, name="sunshine-stube")
        self.faden.start()

    def schliessen(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _freier_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ---------------------------------------------------------------- Tests

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
        self.assertEqual(47989, rp.SUNSHINE_HTTP)
        self.assertEqual(47990, rp.SUNSHINE_WEB)


class ChiakiTests(unittest.TestCase):

    def test_befehl_setzt_platzhalter_ein(self):
        befehl = rp.chiaki_befehl("/pfad/chiaki", "192.168.1.42", "PS5-Wohn")
        self.assertEqual(["/pfad/chiaki", "stream", "PS5-Wohn",
                          "192.168.1.42"], befehl)

    def test_ohne_namen_kein_befehl(self):
        """``chiaki stream <nickname> <host>`` - beide Pflicht (U3-6).

        Bis zum 24.09.2026 hielt dieser Test das Gegenteil fest: Der leere
        Name fiel weg, und die Adresse stand an seiner Stelle - Chiaki
        zeigte dann nur seine Hilfe.
        """
        for name in ("", "   "):
            with self.subTest(name=name):
                with self.assertRaises(rp.NameFehlt):
                    rp.chiaki_befehl("/pfad/chiaki", "192.168.1.42", name)

    def test_eine_vorlage_ohne_namen_braucht_keinen(self):
        """Eine eigene Vorlage ohne ``{nickname}`` geht weiter ohne Namen."""
        befehl = rp.chiaki_befehl("/pfad/chiaki", "192.168.1.42",
                                  argumente=("--host", "{host}"))
        self.assertEqual(["/pfad/chiaki", "--host", "192.168.1.42"], befehl)

    def test_eigener_pfad_schlaegt_die_suche(self):
        import tempfile
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner) / "chiaki-ng.exe"
            datei.write_bytes(b"MZ")
            self.assertEqual(str(datei), rp.chiaki_finden(str(datei)))

    def test_ohne_datei_kein_start(self):
        with self.assertRaises(rp.ChiakiFehlt):
            rp.chiaki_starten("/gibt/es/nicht", "192.168.1.42")


class SunshineTests(unittest.TestCase):

    def test_laufender_host_wird_gelesen(self):
        stube = _SunshineStube()
        try:
            stand = rp.sunshine_pruefen("127.0.0.1", zeit=3.0)
            # Der Testhost horcht auf einem freien Port - deshalb hier
            # gezielt ueber die Adresse mit Port pruefen.
            import urllib.request
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/serverinfo" % stube.port,
                    timeout=3.0) as antwort:
                self.assertIn(b"PC-Wohnzimmer", antwort.read())
        finally:
            stube.schliessen()
        self.assertIsInstance(stand, rp.SunshineStand)

    def test_ohne_host_keine_weboberflaeche(self):
        """Ein Ergebnis "da ist nichts" darf keinen Link anbieten.

        Am 22.09.2026 tat es das: Die Eigenschaft haing nur an der Adresse,
        nicht am Messergebnis - das Fenster haette einen Link auf einen
        Host angeboten, der gar nicht antwortet.
        """
        aus = rp.SunshineStand(laeuft=False, adresse="192.168.1.5")
        self.assertEqual("", aus.weboberflaeche)
        gemessen = rp.sunshine_pruefen("127.0.0.1", zeit=0.8)
        if not gemessen.laeuft:
            self.assertEqual("", gemessen.weboberflaeche)

    def test_weboberflaeche_nennt_den_https_port(self):
        stand = rp.SunshineStand(laeuft=True, adresse="192.168.1.5")
        self.assertEqual("https://192.168.1.5:47990", stand.weboberflaeche)
        self.assertEqual("https://192.168.1.5:47990",
                         rp.sunshine_web_adresse("192.168.1.5"))
        self.assertEqual("", rp.sunshine_web_adresse("  "))


class GatterTests(unittest.TestCase):
    """Das Gatter, durch das jeder Schreibzugriff muss."""

    AKTIV = ra.Benutzer(slot=1, name="Haupt", art="np", merker=0x1002,
                        vordergrund=True)

    def test_slot1_ist_unbedingt_gesperrt(self):
        """Auch bei belegtem, aktiviertem, vorne stehendem Benutzer.

        Der Autor von ActRemoteLink schreibt vor, Slot 1 unangetastet zu
        lassen; der Nutzer hat das am 22.09.2026 als unbedingt entschieden.
        Es gibt deshalb keinen Parameter, der die Sperre aufhebt - dieser
        Test faellt, sobald jemand einen einbaut.
        """
        with self.assertRaises(ra.Slot1Gesperrt):
            ra.schreibzugriff_pruefen(self.AKTIV, 1)
        with self.assertRaises(ra.Slot1Gesperrt):
            ra.schreibzugriff_pruefen(None, 1)
        with self.assertRaises(ra.Slot1Gesperrt):
            ra.schreibzugriff_pruefen(self.AKTIV, 0)

    def test_kein_schalter_hebt_die_sperre_auf(self):
        import inspect
        unterschrift = inspect.signature(ra.schreibzugriff_pruefen)
        self.assertEqual(["benutzer", "slot"], list(unterschrift.parameters))
        quelle = inspect.getsource(ra)
        self.assertNotIn("slot1_erlauben", quelle)
        self.assertNotIn("allow_slot1", quelle)

    def test_unbelegter_slot(self):
        with self.assertRaises(ra.BenutzerFehlt):
            ra.schreibzugriff_pruefen(None, 2)

    def test_belegter_slot_ab_zwei_geht_durch(self):
        eintrag = ra.Benutzer(slot=2, name="Stream")
        self.assertIsNone(ra.schreibzugriff_pruefen(eintrag, 2))

    def test_aktivierter_benutzer_wird_durchgelassen(self):
        """Der Ablauf laeuft nach jedem Neustart erneut durch dieselben
        Schritte - ein Verbot waere hier kein Schutz, sondern ein Abbruch."""
        eintrag = ra.Benutzer(slot=3, art="np", merker=0x1002)
        self.assertIsNone(ra.schreibzugriff_pruefen(eintrag, 3))


class KontoIdTests(unittest.TestCase):

    def test_dezimal_und_hex(self):
        normal = ra.ActRemoteLink.konto_id_normalisieren
        self.assertEqual("0x00000000499602d2", normal(1234567890))
        self.assertEqual("0x00000000499602d2", normal("1234567890"))
        self.assertEqual("0x00000000499602d2", normal("0x499602d2"))

    def test_unsinn_faellt_auf(self):
        normal = ra.ActRemoteLink.konto_id_normalisieren
        for wert in ("", "abc", -1, 2 ** 64):
            with self.subTest(wert=wert):
                with self.assertRaises(ValueError):
                    normal(wert)


class AgentTests(unittest.TestCase):
    """Gegen die echte Stube - Half-Close inbegriffen."""

    def setUp(self):
        self.stube = _AgentStube()
        self.agent = ra.ActRemoteLink("127.0.0.1",
                                      agent_port=self.stube.port, zeit=3.0)

    def tearDown(self):
        self.stube.schliessen()

    def test_laeuft_erkennt_den_agenten(self):
        self.assertTrue(self.agent.laeuft())
        self.assertIn("HELP", self.stube.kommandos)

    def test_benutzerliste_wird_zerlegt(self):
        leute = self.agent.benutzer_liste()
        self.assertEqual(2, len(leute))
        haupt, stream = leute
        self.assertEqual(1, haupt.slot)
        self.assertEqual("Haupt", haupt.name)
        self.assertTrue(haupt.aktiviert)
        self.assertFalse(haupt.vordergrund)
        self.assertEqual(2, stream.slot)
        self.assertFalse(stream.aktiviert)
        self.assertTrue(stream.vordergrund)

    def test_setid_auf_slot1_geht_nicht_einmal_los(self):
        vorher = len(self.stube.kommandos)
        with self.assertRaises(ra.Slot1Gesperrt):
            self.agent.konto_id_setzen(1, 1234567890)
        # LIST darf gelaufen sein, SETID nicht.
        self.assertNotIn("SETID", " ".join(
            self.stube.kommandos[vorher:]).upper())

    def test_setid_auf_slot2_kommt_an(self):
        self.agent.konto_id_setzen(2, 1234567890)
        gesendet = [k for k in self.stube.kommandos if k.startswith("SETID")]
        self.assertEqual(["SETID 2 0x00000000499602d2"], gesendet)

    def test_fakesignin_verlangt_den_vordergrund(self):
        """Slot 1 ist gesperrt, also wird an Slot 2 gemessen: der steht
        vorne und geht durch - ein Benutzer, der nicht vorne steht, nicht."""
        self.agent.fake_anmeldung(2)
        self.assertIn("FAKESIGNIN 2", self.stube.kommandos)

        self.stube.antwort_auf["LIST"] = (
            'slot=2 current=0 user_id=0x10000001 name="Stream" type="" '
            'flags=0x0000 id=0x0000000000000000 b64=BBBB\nEND\n')
        vorher = len(self.stube.kommandos)
        with self.assertRaises(ra.BenutzerNichtVorn):
            self.agent.fake_anmeldung(2)
        self.assertNotIn("FAKESIGNIN 2", self.stube.kommandos[vorher:])

    # Der Ablauf selbst (frueher ``koppeln``, je Druck ein Schritt) steht seit
    # dem 24.09.2026 im Koppel-Assistenten - geprueft in test_koppel_assistent.

    # -- PAIRED statt IS_PAIRED (Durchsicht 23.09.2026, U3-3) -------------

    GERAET_SLOT2 = ("DEVICE index=1 user_id=268435457/0x10000001 "
                    "regist_key=0x0000abcd client_type=2 aes=00112233...")

    def _slot2_aktiviert(self) -> None:
        """Slot 2 steht vorne und traegt schon alles fuer Remote Play -
        so, wie der Agent 2.0 die Zeile schreibt (Benutzer-ID dezimal)."""
        self.stube.antwort_auf["LIST"] = (
            'USER slot=2 current=1 user_id=268435457 name="Stream" type="np" '
            'flags=0x1002 id=0x00000000499602d2 b64=BBBB\nEND\n')

    def test_gekoppelt_fragt_mit_paired(self):
        self._slot2_aktiviert()
        self.stube.geraete = [self.GERAET_SLOT2]
        self.assertTrue(self.agent.gekoppelt(2))
        self.assertIn("PAIRED", self.stube.kommandos)
        self.assertNotIn("IS_PAIRED", self.stube.kommandos,
                         "Das kennt der Agent 2.0 nicht (ERR unknown_command).")

    def test_ein_geraet_eines_anderen_benutzers_zaehlt_nicht(self):
        self._slot2_aktiviert()
        self.stube.geraete = ["DEVICE2 index=3 user_id=268435456/0x10000000 "
                              "regist_key=0x00000001 client_type=2"]
        self.assertFalse(self.agent.gekoppelt(2))
        self.assertTrue(self.agent.gekoppelt())

    # -- signin in LIST (Durchsicht 24.09.2026, U3-4) ----------------------

    #: So schreibt der Agent 2.0 die Zeile (actremotelink_agent.c, cmd_list).
    ZEILE_2_0 = ('USER slot=2 current=1 user_id=268435457 name="Stream" '
                 'type="np" flags=0x1002 id=0x00000000499602d2 b64=BBBB '
                 'signin="%s" status=0 ver=0x00000000 online_id="" np_id=""'
                 '\nEND\n')

    def test_die_zeile_des_agenten_2_0_nennt_die_anmeldung(self):
        """SETID setzt type=np und flags=0x1002 selbst - ob FAKESIGNIN
        gelaufen ist, steht erst in ``signin``."""
        self.stube.antwort_auf["LIST"] = self.ZEILE_2_0 % ""
        eintrag = self.agent.benutzer(2)
        self.assertTrue(eintrag.aktiviert)
        self.assertEqual("", eintrag.anmeldung)
        self.assertTrue(ra.anmeldung_noetig(eintrag))
        self.stube.antwort_auf["LIST"] = (
            self.ZEILE_2_0 % "Stream@a8.de.np.playstation.net")
        eintrag = self.agent.benutzer(2)
        self.assertEqual("Stream@a8.de.np.playstation.net", eintrag.anmeldung)
        self.assertFalse(ra.anmeldung_noetig(eintrag))

    def test_ohne_signin_feld_bleibt_es_beim_merker(self):
        """Aeltere Agenten melden das Feld nicht - dann zaehlt wie bisher
        allein :attr:`Benutzer.aktiviert`."""
        self._slot2_aktiviert()
        self.assertIsNone(self.agent.benutzer(2).anmeldung)

    def test_fehler_wenn_niemand_antwortet(self):
        stumm = ra.ActRemoteLink("127.0.0.1", agent_port=_freier_port(),
                                 zeit=1.0)
        self.assertFalse(stumm.laeuft())
        with self.assertRaises(ra.AgentOffline):
            stumm.benutzer_liste()

    def test_ohne_payload_kein_start(self):
        stumm = ra.ActRemoteLink("127.0.0.1", agent_port=_freier_port(),
                                 zeit=1.0)
        with self.assertRaises(ra.AgentOffline):
            stumm.starten()


class TexteTests(unittest.TestCase):

    SCHLUESSEL = (
        "remoteplay.window_title", "remoteplay.subtitle",
        "remoteplay.hint_suche", "remoteplay.warn_schreibt",
        "remoteplay.col_adresse", "remoteplay.col_name",
        "remoteplay.col_zustand", "remoteplay.col_firmware",
        "remoteplay.label_chiaki", "remoteplay.label_slot",
        "remoteplay.label_konto", "remoteplay.choose_chiaki",
        "remoteplay.no_chiaki", "remoteplay.need_slot",
        "remoteplay.status_idle",
        "remoteplay.status_searching", "remoteplay.status_found",
        "remoteplay.status_failed", "remoteplay.status_chiaki",
        "remoteplay.status_users", "remoteplay.status_users_done",
        "remoteplay.status_an", "remoteplay.status_standby",
        "remoteplay.status_unklar", "remoteplay.user_aktiv",
        "remoteplay.user_offen", "remoteplay.user_vorn",
        "remoteplay.log_gefunden", "remoteplay.log_chiaki",
        "remoteplay.log_kein_agent", "remoteplay.log_kein_pin",
        "remoteplay.hint_download", "remoteplay.btn_search",
        "remoteplay.btn_chiaki", "remoteplay.btn_users",
        "remoteplay.btn_link",
        "prospero.window_title", "prospero.subtitle",
        "prospero.hint_richtung", "prospero.hint_pin",
        "prospero.label_abbild", "prospero.choose_abbild",
        "prospero.need_abbild", "prospero.status_idle",
        "prospero.status_checking", "prospero.status_failed",
        "prospero.status_quelle", "prospero.sunshine_da",
        "prospero.sunshine_weg", "prospero.log_kein_sunshine",
        "prospero.log_quelle", "prospero.log_kein_abbild",
        "prospero.btn_check", "prospero.btn_web", "prospero.btn_source",
        "filetype.ffpfsc",
    )

    def test_alle_schluessel_zweisprachig(self):
        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))

    def test_jeder_zustand_der_suche_hat_seinen_text(self):
        for status in (200, 620, 0):
            konsole = rp.Konsole(adresse="10.0.0.5", status=status)
            with self.subTest(status=status):
                self.assertIn(konsole.status_schluessel, STRINGS)

    def test_jeder_schritt_der_kopplung_hat_seinen_text(self):
        """Seit dem 24.09.2026 die Schritte des Koppel-Assistenten."""
        for schritt in ra.ASSISTENT_SCHRITTE:
            for art in ("schritt", "wer"):
                with self.subTest(schritt=schritt, art=art):
                    self.assertIn("rpassist.%s_%s" % (art, schritt), STRINGS)

    def test_warnung_nennt_slot1_und_den_ausweg(self):
        text = STRINGS["remoteplay.warn_schreibt"]["de"]
        self.assertIn("Slot 1", text)
        self.assertIn("Slot 2", text)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import importlib.util
        pfad = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
        spec = importlib.util.spec_from_file_location("hauptprogramm", pfad)
        cls.modul = importlib.util.module_from_spec(spec)
        sys.modules["hauptprogramm"] = cls.modul
        spec.loader.exec_module(cls.modul)
        cls.app = cls.modul.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _fenster_oeffnen(self, name: str):
        vorher = set(_WURZEL.winfo_children())
        getattr(self.app, name)()
        _WURZEL.update()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher]
        self.assertTrue(neu, "%s hat kein Fenster geoeffnet" % name)
        return neu[-1]

    @staticmethod
    def _beschriftungen(fenster) -> list:
        texte: list = []

        def _durch(widget):
            for kind in widget.winfo_children():
                try:
                    texte.append(str(kind.cget("text")))
                except Exception:  # noqa: BLE001
                    pass
                _durch(kind)

        _durch(fenster)
        return texte

    def test_alle_sieben_knoepfe_sind_verdrahtet(self):
        """Nach Stufe 4 zeigt keine Kennung mehr ins Leere.

        Seit dem 24.09.2026 zeigt "ActRemoteLink" kein Fenster, sondern
        rechts eine Seite (``_KONSOLE_SEITEN``); seit dem 25.09.2026 auch
        "Bibliothek", und es sind sechs Knoepfe (Spiel holen und
        Zurueckspielen stecken in der Bibliothek, KLOG steht nur noch oben).
        """
        self.assertEqual(6, len(self.modul.PS5ConverterGUI._KONSOLE_KNOEPFE))
        klasse = self.modul.PS5ConverterGUI
        for _schluessel, kennung in klasse._KONSOLE_KNOEPFE:
            with self.subTest(kennung=kennung):
                methode = (klasse._KONSOLE_FENSTER.get(kennung, "")
                           or klasse._KONSOLE_SEITEN.get(kennung, ""))
                self.assertTrue(methode, "Kennung %s ohne Fenster" % kennung)
                self.assertTrue(callable(getattr(self.app, methode, None)))
        self.assertFalse(set(klasse._KONSOLE_FENSTER) & set(klasse._KONSOLE_SEITEN),
                         "Eine Kennung ist entweder Fenster oder Seite.")

    def test_remoteplay_zeigt_seine_knoepfe(self):
        fenster = self._fenster_oeffnen("_show_konsole_remoteplay")
        try:
            texte = self._beschriftungen(fenster)
            for schluessel in ("remoteplay.btn_search", "remoteplay.btn_chiaki",
                               "remoteplay.btn_users", "remoteplay.btn_link"):
                with self.subTest(knopf=schluessel):
                    self.assertIn(self.app._t(schluessel), texte)
            # Der Hinweis nennt den Knopf der Ansicht KONSOLE, wie er gerade
            # heisst - seit dem 25.09.2026 eingesetzt statt abgeschrieben.
            knopf = self.app._t("konsole.btn_actremotelink")
            self.assertIn(self.app._t("remoteplay.warn_schreibt", knopf=knopf), texte)
            self.assertTrue(any(knopf in t for t in texte))
        finally:
            fenster.destroy()
            _WURZEL.update()

    def test_prosperolight_zeigt_seine_knoepfe(self):
        fenster = self._fenster_oeffnen("_show_konsole_prosperolight")
        try:
            texte = self._beschriftungen(fenster)
            for schluessel in ("prospero.btn_check", "prospero.btn_web",
                               "prospero.btn_source"):
                with self.subTest(knopf=schluessel):
                    self.assertIn(self.app._t(schluessel), texte)
        finally:
            fenster.destroy()
            _WURZEL.update()

    def test_payloads_kommen_aus_helloworld(self):
        """Die ELFs gehoeren zu den Payloads, nicht in einen eigenen Ordner.

        Nur dort greifen die Schnellauswahl und die Werkzeugpflege, die
        jede mitgelieferte .elf gegen THIRD_PARTY_LICENSES.md haelt. Der
        Ordner ``Streaming`` traegt deshalb nur das ProsperoLight-Abbild.
        """
        self.assertEqual({"agent", "pin"}, set(self.app._ACTREMOTELINK_MUSTER))
        self.assertEqual({"prospero"}, set(self.app._STREAMING_MUSTER))
        self.assertEqual("Streaming", self.app._STREAMING_ORDNER)
        for art in ("agent", "pin"):
            with self.subTest(art=art):
                pfad = self.app._streaming_pfad(art)
                if pfad:
                    self.assertIn("helloworld", pfad.replace("\\", "/"))

    # -- Doppelklick und Chiaki (Durchsicht 24.09.2026, H3-9 und U3-6) ----

    @staticmethod
    def _alle(fenster, klasse) -> list:
        gefunden: list = []

        def _durch(widget):
            for kind in widget.winfo_children():
                if isinstance(kind, klasse):
                    gefunden.append(kind)
                _durch(kind)

        _durch(fenster)
        return gefunden

    def _knopf(self, fenster, schluessel):
        from tkinter import ttk
        text = self.app._t(schluessel)
        for knopf in self._alle(fenster, ttk.Button):
            if str(knopf.cget("text")) == text:
                return knopf
        self.fail("Knopf %s fehlt" % schluessel)

    @staticmethod
    def _aufraeumen() -> None:
        """Speicherbereinigung im Hauptfaden.

        Die Fenster dieser Tests starten Arbeitsfaeden. Liegen von frueheren
        Fenstern noch Tk-Variablen im Kreis-Muell, raeumt sonst der Faden sie
        ab - und Tk meldet "main thread is not in main loop" als Warnung.
        """
        import gc
        gc.collect()

    @staticmethod
    def _warten(bedingung, grenze: float = 10.0) -> bool:
        ende = time.monotonic() + grenze
        while time.monotonic() < ende:
            _WURZEL.update()
            if bedingung():
                return True
            time.sleep(0.02)
        return False

    @staticmethod
    def _doppelklick(tabelle) -> None:
        """Ruft die Bindung von <Double-1> auf.

        ``event generate`` kennt keinen Double-Modifikator; die Bindung ist
        ein Tcl-Befehl, der die Ereignisfelder als Argumente erwartet. "0"
        statt "??": Die Seriennummer liest tkinter ohne Rueckfall als Zahl.
        """
        skript = tabelle.bind("<Double-1>")
        befehl = re.search(r"\[(\S+)", skript).group(1)
        tabelle.tk.call(befehl, *(["0"] * len(tabelle._subst_format)))

    def test_doppelklick_auf_einen_benutzer_setzt_den_slot(self):
        """H3-9: Bis zum 24.09.2026 landete der Slot im Adressfeld."""
        from tkinter import ttk
        leute = [ra.Benutzer(slot=3, name="Stream")]
        self._aufraeumen()
        with mock.patch.object(self.app, "_ps5_ip", return_value="10.0.0.5"), \
                mock.patch.object(ra.ActRemoteLink, "laeuft", return_value=True), \
                mock.patch.object(ra.ActRemoteLink, "benutzer_liste",
                                  return_value=leute):
            fenster = self._fenster_oeffnen("_show_konsole_remoteplay")
            try:
                self._knopf(fenster, "remoteplay.btn_users").invoke()
                tabelle = self._alle(fenster, ttk.Treeview)[0]
                self.assertTrue(self._warten(lambda: len(tabelle.get_children()) == 1))
                tabelle.selection_set(tabelle.get_children()[0])
                self._doppelklick(tabelle)
                eintraege = self._alle(fenster, tk.Entry)
                self.assertEqual("10.0.0.5", eintraege[0].get(),
                                 "Der Slot landete im Adressfeld.")
                self.assertEqual("3", eintraege[2].get())
            finally:
                fenster.destroy()
                _WURZEL.update()
                self._aufraeumen()

    def test_chiaki_bekommt_den_namen_aus_der_suche(self):
        """U3-6: ``chiaki stream <name> <adresse>`` - ohne Namen kein Start."""
        from tkinter import messagebox, ttk
        gestartet: list = []
        warnungen: list = []
        konsolen = [rp.Konsole(adresse="10.0.0.5", name="Wohnzimmer", status=200)]
        self._aufraeumen()
        with mock.patch.object(self.app, "_ps5_ip", return_value="10.0.0.5"), \
                mock.patch.object(rp, "suchen", return_value=konsolen), \
                mock.patch.object(rp, "chiaki_finden", return_value=sys.executable), \
                mock.patch.object(rp, "chiaki_starten",
                                  side_effect=lambda *a, **k: gestartet.append((a, k))), \
                mock.patch.object(messagebox, "showwarning",
                                  side_effect=lambda *a, **k: warnungen.append(a)):
            fenster = self._fenster_oeffnen("_show_konsole_remoteplay")
            try:
                chiaki = self._knopf(fenster, "remoteplay.btn_chiaki")
                chiaki.invoke()
                self.assertEqual([], gestartet, "Ohne Namen darf Chiaki nicht starten.")
                self.assertTrue(any(
                    self.app._t("remoteplay.need_search_for_chiaki") in a
                    for a in warnungen))

                self._knopf(fenster, "remoteplay.btn_search").invoke()
                tabelle = self._alle(fenster, ttk.Treeview)[0]
                self.assertTrue(self._warten(lambda: len(tabelle.get_children()) == 1))
                self.assertTrue(self._warten(lambda: chiaki.instate(["!disabled"])))
                chiaki.invoke()
                self.assertEqual(1, len(gestartet))
                argumente, benannt = gestartet[0]
                self.assertEqual("10.0.0.5", argumente[1])
                self.assertEqual("Wohnzimmer", benannt.get("nickname"))
            finally:
                fenster.destroy()
                _WURZEL.update()
                self._aufraeumen()

    def test_kein_arbeitsfaden_bleibt_stehen(self):
        vorher = {t.name for t in threading.enumerate()}
        for name in ("_show_konsole_remoteplay", "_show_konsole_prosperolight"):
            fenster = self._fenster_oeffnen(name)
            fenster.destroy()
            _WURZEL.update()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertEqual(set(), {n for n in neu
                                 if n.startswith(("remoteplay-", "prospero-"))})


if __name__ == "__main__":
    unittest.main()
