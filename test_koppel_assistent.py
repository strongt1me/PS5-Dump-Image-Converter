# -*- coding: utf-8 -*-
"""Der Koppel-Assistent fuer Remote Play (ActRemoteLink), 24.09.2026.

Vier Wuensche des Nutzers an einem Tag:

* "falls die elf's nicht mitgeliefert werden duerfen": Fehlt ein Payload,
  nennt das Programm die Download-Adresse des Releases v2.0 und oeffnet sie
  auf Klick - heruntergeladen wird nichts von selbst.
* "Ist eine Reihenfolge wichtig bei den elfs, sollte es klar angezeigt
  werden": Der Ablauf steht als nummerierte Liste da, je Schritt, wer ihn
  erledigt und welches Payload dabei geschickt wird.
* "damit alles automatisch ablaeuft": Der Assistent geht die Schritte selbst
  durch und wartet, wo nur der Anwender an der PS5 weiterkommt.
* "in die rechte Seite verlegen": Er steht rechts in der Ansicht KONSOLE,
  hinter dem Knopf "ActRemoteLink" (bis 25.09.2026 Nummer 8, seither 6).

Gemessen wird gegen eine Konsole im Kleinen (:class:`_Konsole`): das
Agent-Protokoll auf einem echten TCP-Port, Benutzer, die SETID und
FAKESIGNIN wirklich veraendern, ein Vordergrund, der wechseln kann, und ein
Neustart, der den Agenten beendet - so, wie sich actremotelink_agent.c 2.0
verhaelt. Die Ausgabe des PIN-Payloads kommt aus vorbereiteten Stuecken im
Format von actremotelink_pin_notify.c.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import re
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("koppel_assistent")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import payload_versand             # noqa: E402
from ps5_validator.utils import remoteplay_agent as ra      # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

ADRESSE = ("https://github.com/francoataffarel/ActRemoteLink/releases/"
           "download/v2.0/ActRemoteLink.zip")
AGENT_ELF = "C:/x/actremotelink_agent_v2.0.elf"
PIN_ELF = "C:/x/actremotelink_pin_notify_v2.0.elf"

#: So schreibt das PIN-Payload 2.0 (actremotelink_pin_notify.c, README).
PIN_AUSGABE = ("ActRemoteLink: initializing Remote Play...\n"
               "OK PIN\nslot=2\npin=2836 0549\npin_raw=28360549\n"
               "account_id_hex=0x8f1e2d3c4b5a6978\n"
               "account_id_base64=eGlaSzwtHo8=\ntimeout=300\nEND\n")
ZWEITE_PIN = PIN_AUSGABE.replace("2836 0549", "1111 2222").replace(
    "28360549", "11112222")


def _b64(konto: int) -> str:
    """Wie account_id_to_base64 im Agent: die 8 Bytes in Speicherfolge."""
    return base64.b64encode(struct.pack("<Q", konto)).decode("ascii")


def _frisch(name: str, user_id: int) -> dict:
    """Ein neu angelegter lokaler Benutzer - ohne account_id."""
    return {"name": name, "user_id": user_id, "konto": 0, "art": "",
            "merker": 0x10000, "signin": ""}


def _fertig(name: str, user_id: int, konto: int) -> dict:
    """Ein Benutzer mit account_id und Offline-Anmeldung."""
    return {"name": name, "user_id": user_id, "konto": konto, "art": "np",
            "merker": 0x1002, "signin": "%s@a8.de.np.playstation.net" % name}


class _Konsole:
    """Eine PS5 im Kleinen: der Agent 2.0 und seine Benutzer."""

    def __init__(self) -> None:
        self.schloss = threading.Lock()
        self.benutzer: dict = {
            1: _fertig("Haupt", 0x10000000, 0x0123456789ABCDEF),
            2: _frisch("Stream", 0x10000001),
        }
        self.vorn = 2
        #: Bis ihn jemand schickt, laeuft kein Agent.
        self.agent_an = False
        #: Agent 2.0 meldet ``signin=`` in LIST, aeltere nicht.
        self.signin_feld = True
        self.gekoppelt: set = set()
        #: Ohne Ausgabe des PIN-Payloads: nach so vielen PAIRED-Fragen
        #: meldet die Konsole das Geraet (Chiaki hat die PIN eingegeben).
        self.koppeln_nach_fragen = None
        self.paired_fragen = 0
        self.kommandos: list = []
        self.gesendet: list = []
        self.horcher = socket.socket()
        self.horcher.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(16)
        self.port = self.horcher.getsockname()[1]
        threading.Thread(target=self._bedienen, daemon=True,
                         name="konsolen-stube").start()

    # -- Was die Tests an der Konsole tun -------------------------------

    def senden(self, pfad: str) -> "tuple[bool, str]":
        """Wie ``_send_payload_to_ps5``: Das Payload kommt an und laeuft."""
        name = Path(pfad).name
        with self.schloss:
            self.gesendet.append(name)
            if "agent" in name:
                self.agent_an = True
        return True, ""

    def neustart(self, anmeldung_vergessen: bool = False) -> None:
        """Die PS5 startet neu: Der Agent ist weg."""
        with self.schloss:
            self.agent_an = False
            if anmeldung_vergessen:
                for eintrag in self.benutzer.values():
                    if eintrag["name"] != "Haupt":
                        eintrag["signin"] = ""

    def zaehle(self, anfang: str) -> int:
        with self.schloss:
            return sum(1 for k in self.kommandos if k.startswith(anfang))

    def schliessen(self) -> None:
        try:
            self.horcher.close()
        except OSError:
            pass

    # -- Das Protokoll ----------------------------------------------------

    def _bedienen(self) -> None:
        while True:
            try:
                verbindung, _ = self.horcher.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(verbindung,),
                             daemon=True).start()

    def _sitzung(self, verbindung: socket.socket) -> None:
        verbindung.settimeout(5.0)
        teile: list = []
        try:
            while True:
                brocken = verbindung.recv(1024)
                if not brocken:
                    break        # Half-Close: das Kommando ist vollstaendig
                teile.append(brocken)
        except OSError:
            pass
        antwort = self._antwort(b"".join(teile).decode("utf-8", "replace").strip())
        try:
            if antwort is not None:
                verbindung.sendall(antwort.encode("utf-8"))
        except OSError:
            pass
        finally:
            verbindung.close()

    def _zeile(self, slot: int) -> str:
        b = self.benutzer[slot]
        zeile = ('USER slot=%d current=%d user_id=%d name="%s" type="%s" '
                 'flags=0x%04x id=0x%016x b64=%s'
                 % (slot, 1 if slot == self.vorn else 0, b["user_id"],
                    b["name"], b["art"], b["merker"], b["konto"],
                    _b64(b["konto"])))
        if self.signin_feld:
            zeile += (' signin="%s" status=0 ver=0x00000000 online_id="" '
                      'np_id=""' % b["signin"])
        return zeile + "\n"

    def _antwort(self, kommando: str) -> "str | None":
        with self.schloss:
            if not self.agent_an:
                return None          # kein Agent: niemand antwortet
            self.kommandos.append(kommando)
            teile = kommando.split()
            wort = teile[0].upper() if teile else ""
            if wort == "HELP":
                return "OK HELP\nLIST\nSETID <slot> <hex>\nFAKESIGNIN <slot>\nEND\n"
            if wort == "LIST":
                return ("OK LIST\n"
                        + "".join(self._zeile(s) for s in sorted(self.benutzer))
                        + "END\n")
            if wort == "SETID":
                slot, wert = int(teile[1]), int(teile[2], 0)
                self.benutzer[slot].update(konto=wert, art="np", merker=0x1002)
                return "OK SETID\nslot=%d\nreboot_recommended=1\nEND\n" % slot
            if wort == "FAKESIGNIN":
                slot = int(teile[1])
                if slot != self.vorn:
                    return ("ERR fake_signin target_slot_mismatch active_slot_is_"
                            "%d_please_switch_user_on_ps5\nEND\n" % self.vorn)
                if not self.benutzer[slot]["konto"]:
                    return "ERR fake_signin user_not_activated_aborting\nEND\n"
                self.benutzer[slot]["signin"] = (
                    "%s@a8.de.np.playstation.net" % self.benutzer[slot]["name"])
                return "OK FAKESIGNIN\nslot=%d\nreboot_recommended=1\nEND\n" % slot
            if wort == "PREPARE_PIN":
                b = self.benutzer[self.vorn]
                return ("OK PREPARE_PIN\nslot=%d\nremoteplay_enable=1\n"
                        "account_id_hex=0x%016x\naccount_id_base64=%s\nEND\n"
                        % (self.vorn, b["konto"], _b64(b["konto"])))
            if wort == "PAIRED":
                self.paired_fragen += 1
                if (self.koppeln_nach_fragen is not None
                        and self.paired_fragen >= self.koppeln_nach_fragen):
                    self.gekoppelt.add(self.benutzer[self.vorn]["user_id"])
                return ("OK PAIRED\n" + "".join(
                    "DEVICE index=%d user_id=%d/0x%x regist_key=0x1 client_type=2\n"
                    % (nr, u, u) for nr, u in enumerate(sorted(self.gekoppelt), 1))
                    + "END\n")
            if wort == "QUIT":
                self.agent_an = False
                return "OK BYE\nEND\n"
            return "ERR unknown_command\nEND\n"


class _Leser:
    """Wie ``payload_versand.Mitleser`` - mit vorbereiteten Stuecken.

    ``None`` ist Stille; sind die Stuecke aufgebraucht, schliesst die
    "Konsole" die Verbindung - das Payload hat sich beendet.
    """

    def __init__(self, *stuecke) -> None:
        self.stuecke = list(stuecke)
        self.zu = False
        self.geschlossen = False

    def lesen(self) -> str:
        if self.zu:
            return ""
        time.sleep(0.01)
        if not self.stuecke:
            self.zu = True
            return ""
        stueck = self.stuecke.pop(0)
        return "" if stueck is None else stueck

    def schliessen(self) -> None:
        self.zu = True
        self.geschlossen = True


class _Lauf:
    """Laesst den Assistenten in einem Faden laufen und sammelt, was er meldet."""

    def __init__(self, konsole: _Konsole, zustimmen: bool = True,
                 agent_elf: str = AGENT_ELF, pin_elf: str = PIN_ELF,
                 lader: "list | None" = None, **optionen) -> None:
        self.konsole = konsole
        self.ereignisse: list = []
        self.abbrechen = False
        self.fragen: list = []
        #: Antwortet der Payload-Lader? Als Liste, damit ein Test es umlegt.
        self.lader = lader if lader is not None else [True]
        agent = ra.ActRemoteLink("127.0.0.1", agent_port=konsole.port, zeit=2.0,
                                 sende_payload=konsole.senden,
                                 agent_elf=agent_elf, pin_elf=pin_elf)

        def _bestaetigen(eintrag) -> bool:
            self.fragen.append(eintrag.slot)
            return zustimmen

        optionen.setdefault("takt", 0.05)
        self.assistent = ra.Kopplungsassistent(
            agent, melden=self.ereignisse.append, bestaetigen=_bestaetigen,
            abgebrochen=lambda: self.abbrechen,
            lader_erreichbar=lambda: self.lader[0], **optionen)
        self.ergebnis = None
        self.faden = threading.Thread(target=self._laufen, daemon=True,
                                      name="assistent-pruefung")

    def _laufen(self) -> None:
        self.ergebnis = self.assistent.lauf()

    def starten(self) -> "_Lauf":
        self.faden.start()
        return self

    def warten(self, grenze: float = 30.0):
        self.faden.join(grenze)
        if self.faden.is_alive():
            self.abbrechen = True
            self.faden.join(5.0)
            raise AssertionError("Der Assistent kam nicht zum Ende.")
        return self.ergebnis

    def warten_auf(self, bedingung, grenze: float = 20.0):
        ende = time.monotonic() + grenze
        while time.monotonic() < ende:
            for ereignis in list(self.ereignisse):
                if bedingung(ereignis):
                    return ereignis
            if not self.faden.is_alive():
                break
            time.sleep(0.02)
        self.abbrechen = True
        raise AssertionError("Ereignis blieb aus; zuletzt: %r"
                             % (self.ereignisse[-3:],))

    def wartet_auf(self, text: str, grenze: float = 20.0):
        """Bis der Assistent mit dieser Anweisung auf den Anwender wartet."""
        return self.warten_auf(lambda e: e.art == "schritt"
                               and e.zustand == ra.WARTET and e.text == text,
                               grenze)

    def protokolliert(self, text: str) -> bool:
        return any(e.art == "protokoll" and e.text == text
                   for e in self.ereignisse)

    def letzte_anweisung(self):
        schritte = [e for e in self.ereignisse if e.art == "schritt" and e.text]
        return schritte[-1] if schritte else None

    def erledigt(self) -> list:
        """Die Schritte, die fertig wurden - jeder einmal, in ihrer Folge."""
        gesehen: list = []
        for e in self.ereignisse:
            if e.art == "schritt" and e.zustand in (ra.ERLEDIGT, ra.UEBERSPRUNGEN) \
                    and e.schritt not in gesehen:
                gesehen.append(e.schritt)
        return gesehen


class _MitKonsole(unittest.TestCase):
    def setUp(self) -> None:
        self.konsole = _Konsole()
        self.laeufe: list = []

    def tearDown(self) -> None:
        for lauf in self.laeufe:
            lauf.abbrechen = True
            lauf.faden.join(5.0)
        self.konsole.schliessen()

    def _lauf(self, **optionen) -> _Lauf:
        lauf = _Lauf(self.konsole, **optionen)
        self.laeufe.append(lauf)
        return lauf

    def _texte_passen(self, lauf: _Lauf) -> None:
        """Jede Meldung hat ihren Text - in beiden Sprachen, mit allen Werten."""
        for e in lauf.ereignisse:
            if e.art not in ("schritt", "protokoll") or not e.text:
                continue
            for sprache in ("de", "en"):
                with self.subTest(schluessel=e.text, sprache=sprache):
                    self.assertIn(e.text, STRINGS)
                    STRINGS[e.text][sprache].format(**e.werte)


# ---------------------------------------------------------------- Modul

class AdresseTests(unittest.TestCase):
    """Wohin, wenn die Payloads fehlen."""

    def test_die_adresse_des_releases(self) -> None:
        self.assertEqual(ADRESSE, ra.DOWNLOAD_ADRESSE)
        self.assertEqual("https://github.com/francoataffarel/ActRemoteLink",
                         ra.PROJEKT_ADRESSE)

    def test_die_texte_nennen_sie(self) -> None:
        for schluessel in ("remoteplay.hint_download", "remoteplay.log_kein_agent",
                           "remoteplay.log_kein_pin", "rpassist.jetzt_kein_payload"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertIn("{adresse}", STRINGS[schluessel][sprache])

    def test_die_lizenzliste_nennt_die_quelle(self) -> None:
        text = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn(ADRESSE, text)

    def test_das_modul_nennt_sie_beim_fehlen(self) -> None:
        agent = ra.ActRemoteLink("127.0.0.1", agent_elf="", pin_elf="",
                                 sende_payload=lambda _p: (True, ""))
        with mock.patch.object(agent, "laeuft", lambda: False):
            with self.assertRaises(ra.PayloadFehlt) as fehler:
                agent.starten()
        self.assertEqual("actremotelink_agent*.elf", fehler.exception.muster)
        self.assertIn(ADRESSE, str(fehler.exception))
        with self.assertRaises(ra.PayloadFehlt) as fehler:
            agent.pin_senden()
        self.assertEqual("actremotelink_pin_notify*.elf", fehler.exception.muster)
        # Wer bisher AgentOffline faengt, faengt es weiter.
        self.assertIsInstance(fehler.exception, ra.AgentOffline)

    def test_das_programm_sucht_nach_denselben_mustern(self) -> None:
        self.assertEqual(ra.PAYLOAD_MUSTER, APP.PS5ConverterGUI._ACTREMOTELINK_MUSTER)

    #: SHA-256 des unveraenderten GPL-3.0-Textes der FSF (35.149 Bytes) -
    #: derselbe wie ``PS4FFPFSC-0.2.9/LICENSES/MkPFS-GPL-3.0.txt``.
    GPL3_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"

    def test_der_gpl_text_liegt_bei(self) -> None:
        """Wunsch des Nutzers (24.09.2026): Der Wortlaut der GPL liegt bei den
        GPL-Payloads in ``helloworld`` - und damit in jedem Bau, denn alle drei
        Specs betten den ganzen Ordner ein."""
        pfad = PROJEKT / "helloworld" / "LICENSE-GPL-3.0.txt"
        self.assertTrue(pfad.is_file(), "helloworld/LICENSE-GPL-3.0.txt fehlt.")
        self.assertEqual(self.GPL3_SHA256,
                         hashlib.sha256(pfad.read_bytes()).hexdigest(),
                         "Der Lizenztext muss unveraendert beiliegen.")
        liste = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("`helloworld/LICENSE-GPL-3.0.txt`", liste)
        for spec in ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
                     "PS5ImageConverter_Pro_macos.spec"):
            with self.subTest(spec=spec):
                self.assertIn("_datas.append((_helloworld, 'helloworld'))",
                              (PROJEKT / spec).read_text(encoding="utf-8"))


class PinAusgabeTests(unittest.TestCase):
    """Die Ausgabe des PIN-Payloads (actremotelink_pin_notify.c 2.0)."""

    def test_pin_und_konto_id(self) -> None:
        ausgabe = ra.pin_ausgabe_lesen(PIN_AUSGABE)
        self.assertEqual("2836 0549", ausgabe.pin)
        self.assertEqual("eGlaSzwtHo8=", ausgabe.b64)
        self.assertEqual(2, ausgabe.slot)
        self.assertEqual("", ausgabe.ergebnis)

    def test_die_konto_id_passt_zum_agent(self) -> None:
        """Beide rechnen die ID in Speicherfolge um (README-Beispiel)."""
        self.assertEqual("eGlaSzwtHo8=", _b64(0x8F1E2D3C4B5A6978))

    def test_erfolg_und_fehlschlaege(self) -> None:
        for anhang, ergebnis, fehler in (
                ("PAIRING SUCCESS\n", "erfolg", ""),
                ("PAIRING FAILED invalid_pin\n", "falsche_pin", ""),
                ("PAIRING FAILED invalid_account_id\n", "falsche_konto_id", ""),
                ("PAIRING FAILED 0x80fc1234\n", "fehler", "0x80fc1234")):
            with self.subTest(anhang=anhang):
                ausgabe = ra.pin_ausgabe_lesen(PIN_AUSGABE + anhang)
                self.assertEqual(ergebnis, ausgabe.ergebnis)
                self.assertEqual(fehler, ausgabe.fehler)

    def test_startfehler_des_payloads(self) -> None:
        ausgabe = ra.pin_ausgabe_lesen(
            "ActRemoteLink: initializing Remote Play...\n"
            "ActRemoteLink ERROR\nsceRemoteplayInitialize: 0x80020003\n")
        self.assertEqual("fehler", ausgabe.ergebnis)
        self.assertEqual("sceRemoteplayInitialize: 0x80020003", ausgabe.fehler)
        self.assertEqual("", ausgabe.pin)

    def test_prepare_pin_liefert_die_konto_id(self) -> None:
        ausgabe = ra.pin_ausgabe_lesen(
            "OK PREPARE_PIN\r\nslot=3\r\nremoteplay_enable=1\r\n"
            "account_id_hex=0x0000000000000001\r\naccount_id_base64=AQAAAAAAAAA=\r\n"
            "next_step=Open Settings > System > Remote Play > Link Device\r\nEND\r\n")
        self.assertEqual("AQAAAAAAAAA=", ausgabe.b64)
        self.assertEqual(3, ausgabe.slot)
        self.assertEqual("", ausgabe.pin)


class EntscheidungTests(unittest.TestCase):
    """Wann SETID, wann FAKESIGNIN - an dem, was LIST meldet."""

    def test_ohne_account_id_braucht_es_setid(self) -> None:
        """Ohne ID bricht FAKESIGNIN ab (user_not_activated_aborting). Bis
        zum 24.09.2026 ging ``koppeln`` ohne Angabe gleich dorthin."""
        frisch = ra.Benutzer(slot=2, konto_id="0x0000000000000000")
        self.assertEqual((True, None), ra.setid_noetig(frisch))
        self.assertEqual((True, "0x00000000499602d2"),
                         ra.setid_noetig(frisch, "0x00000000499602d2"))

    def test_vorhandene_id_bleibt(self) -> None:
        fertig = ra.Benutzer(slot=2, konto_id="0x00000000499602d2", art="np",
                             merker=0x1002)
        self.assertEqual((False, None), ra.setid_noetig(fertig))
        self.assertEqual((False, None), ra.setid_noetig(fertig, "0x00000000499602D2"))
        self.assertEqual((True, "0x0000000000000007"),
                         ra.setid_noetig(fertig, "0x0000000000000007"))

    def test_id_ohne_typ_und_merker_wird_neu_gesetzt(self) -> None:
        halb = ra.Benutzer(slot=2, konto_id="0x00000000499602d2", art="",
                           merker=0)
        self.assertEqual((True, "0x00000000499602d2"), ra.setid_noetig(halb))

    def test_anmeldung_nach_dem_signin_feld(self) -> None:
        """U3-4: SETID macht den Benutzer "aktiviert" - angemeldet ist er
        erst, wenn LIST ``signin`` meldet."""
        aktiviert = dict(slot=2, konto_id="0x1", art="np", merker=0x1002)
        self.assertTrue(ra.anmeldung_noetig(ra.Benutzer(anmeldung="", **aktiviert)))
        self.assertFalse(ra.anmeldung_noetig(
            ra.Benutzer(anmeldung="Stream@a8.de.np.playstation.net", **aktiviert)))
        # Aeltere Agenten melden kein signin (und kennen kein FAKESIGNIN).
        self.assertFalse(ra.anmeldung_noetig(ra.Benutzer(anmeldung=None, **aktiviert)))
        self.assertTrue(ra.anmeldung_noetig(ra.Benutzer(slot=2, anmeldung=None)))

    def test_neue_konto_id(self) -> None:
        ids = {ra.neue_konto_id() for _ in range(50)}
        self.assertEqual(50, len(ids))
        for wert in ids:
            self.assertRegex(wert, r"^0x[0-9a-f]{16}$")
            self.assertNotEqual(0, int(wert, 16))

    def test_account_id_0_und_unsinn_werden_abgewiesen(self) -> None:
        agent = ra.ActRemoteLink("127.0.0.1")
        for wert in ("0", "0x0", "abc", "-5"):
            with self.subTest(wert=wert):
                with self.assertRaises(ValueError):
                    ra.Kopplungsassistent(agent, konto_id=wert)


class _LaderStube:
    """Wie elfldr: nimmt ein ELF bis zum Half-Close und schreibt dann die
    Ausgabe des Payloads zurueck - Stueck fuer Stueck, mit Pausen."""

    def __init__(self, *stuecke, pause: float = 0.05) -> None:
        self.stuecke = [s.encode("utf-8") if isinstance(s, str) else s
                        for s in stuecke]
        self.pause = pause
        self.empfangen = b""
        self.horcher = socket.socket()
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(1)
        self.port = self.horcher.getsockname()[1]
        threading.Thread(target=self._bedienen, daemon=True,
                         name="lader-stube").start()

    def _bedienen(self) -> None:
        try:
            verbindung, _ = self.horcher.accept()
        except OSError:
            return
        with verbindung:
            teile = []
            while True:
                brocken = verbindung.recv(65536)
                if not brocken:
                    break
                teile.append(brocken)
            self.empfangen = b"".join(teile)
            for stueck in self.stuecke:
                time.sleep(self.pause)
                verbindung.sendall(stueck)

    def schliessen(self) -> None:
        self.horcher.close()


class MitleserTests(unittest.TestCase):
    """``payload_versand.Mitleser`` gegen einen echten Horcher."""

    def _alles(self, leser, grenze: float = 10.0) -> str:
        text = ""
        ende = time.monotonic() + grenze
        while not leser.zu and time.monotonic() < ende:
            text += leser.lesen()
        return text

    def test_liest_stueckweise_bis_zum_ende(self) -> None:
        stube = _LaderStube("OK PIN\n", "pin=1234 5678\n", "PAIRING SUCCESS\n")
        self.addCleanup(stube.schliessen)
        leser = payload_versand.Mitleser("127.0.0.1", b"\x7fELF-daten",
                                         port=stube.port, takt=0.2)
        try:
            self.assertEqual("OK PIN\npin=1234 5678\nPAIRING SUCCESS\n",
                             self._alles(leser))
        finally:
            leser.schliessen()
        self.assertEqual(b"\x7fELF-daten", stube.empfangen)

    def test_stille_ist_nicht_das_ende(self) -> None:
        stube = _LaderStube("spaet\n", pause=1.0)
        self.addCleanup(stube.schliessen)
        leser = payload_versand.Mitleser("127.0.0.1", b"ELF", port=stube.port,
                                         takt=0.1)
        try:
            self.assertEqual("", leser.lesen())
            self.assertFalse(leser.zu)
            self.assertEqual("spaet\n", self._alles(leser))
        finally:
            leser.schliessen()

    def test_umlaute_ueber_stueckgrenzen(self) -> None:
        roh = "Grüße\n".encode("utf-8")
        stube = _LaderStube(roh[:3], roh[3:])
        self.addCleanup(stube.schliessen)
        leser = payload_versand.Mitleser("127.0.0.1", b"ELF", port=stube.port,
                                         takt=0.2)
        try:
            self.assertEqual("Grüße\n", self._alles(leser))
        finally:
            leser.schliessen()

    def test_ohne_lader_scheitert_schon_der_erzeuger(self) -> None:
        frei = socket.socket()
        frei.bind(("127.0.0.1", 0))
        port = frei.getsockname()[1]
        frei.close()
        with self.assertRaises(OSError):
            payload_versand.Mitleser("127.0.0.1", b"ELF", port=port, timeout=2.0)


# ---------------------------------------------------------------- Ablauf

class AblaufTests(_MitKonsole):
    """Der ganze Ablauf gegen die Konsole im Kleinen."""

    def test_ein_frischer_benutzer_wird_ganz_gekoppelt(self) -> None:
        k = self.konsole
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, None, "PAIRING SUCCESS\n")).starten()
        lauf.wartet_auf("rpassist.jetzt_neustart")
        # Vor dem Neustart: SETID mit einer erzeugten ID, gleich danach
        # FAKESIGNIN (ohne Neustart dazwischen) - und genau eine Rueckfrage.
        setid = [c for c in k.kommandos if c.startswith("SETID")]
        self.assertEqual(1, len(setid))
        self.assertRegex(setid[0], r"^SETID 2 0x[0-9a-f]{16}$")
        self.assertLess(k.kommandos.index(setid[0]), k.kommandos.index("FAKESIGNIN 2"))
        self.assertEqual([2], lauf.fragen)
        self.assertEqual(0, k.zaehle("PREPARE_PIN"), "PIN vor dem Neustart")

        k.neustart()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(2, k.gesendet.count(Path(AGENT_ELF).name),
                         "Nach dem Neustart muss der Agent neu geschickt werden.")
        pins = [e.werte for e in lauf.ereignisse if e.art == "pin" and e.werte["pin"]]
        self.assertEqual("2836 0549", pins[-1]["pin"])
        self.assertEqual("eGlaSzwtHo8=", pins[-1]["b64"])
        self.assertEqual([True, False], [e.werte["neustart_offen"]
                                         for e in lauf.ereignisse if e.art == "merken"])
        self.assertEqual(list(ra.ASSISTENT_SCHRITTE), lauf.erledigt())
        self.assertEqual("rpassist.jetzt_fertig", lauf.letzte_anweisung().text)
        self.assertIn("QUIT", k.kommandos, "Der Agent wird am Ende beendet.")
        self.assertTrue(lauf.protokolliert("rpassist.log_konto_neu"))
        self.assertTrue(any(e.art == "ausgabe" and e.text == "PAIRING SUCCESS"
                            for e in lauf.ereignisse))
        self._texte_passen(lauf)

    def test_was_schon_da_ist_wird_nicht_geschrieben(self) -> None:
        k = self.konsole
        k.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)
        k.gekoppelt.add(0x10000001)
        lauf = self._lauf().starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(0, k.zaehle("SETID") + k.zaehle("FAKESIGNIN"))
        self.assertEqual([], lauf.fragen, "Ohne Schreiben keine Rueckfrage.")
        self.assertTrue(lauf.protokolliert("rpassist.log_schon_gekoppelt"))
        self.assertNotIn("IS_PAIRED", k.kommandos,
                         "Das kennt der Agent 2.0 nicht (U3-3).")
        self._texte_passen(lauf)

    def test_eigene_account_id_wird_gesetzt(self) -> None:
        k = self.konsole
        lauf = self._lauf(konto_id="1234567890").starten()
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertIn("SETID 2 0x00000000499602d2", k.kommandos)
        self.assertFalse(lauf.protokolliert("rpassist.log_konto_neu"))

    def test_doppelte_account_id_wird_abgewiesen(self) -> None:
        k = self.konsole
        k.benutzer[3] = _fertig("Andere", 0x10000002, 0x499602D2)
        lauf = self._lauf(konto_id="0x499602d2").starten()
        self.assertEqual("fehler", lauf.warten())
        self.assertEqual("rpassist.jetzt_id_doppelt", lauf.letzte_anweisung().text)
        self.assertEqual(3, lauf.letzte_anweisung().werte["slot"])
        self.assertEqual(0, k.zaehle("SETID"))
        self._texte_passen(lauf)

    def test_slot1_bleibt_gesperrt(self) -> None:
        lauf = self._lauf(slot=1).starten()
        self.assertEqual("fehler", lauf.warten())
        self.assertEqual("rpassist.jetzt_slot1", lauf.letzte_anweisung().text)
        self.assertEqual(0, self.konsole.zaehle("SETID") + self.konsole.zaehle("FAKESIGNIN"))

    def test_rueckfrage_verneint_schreibt_nichts(self) -> None:
        lauf = self._lauf(zustimmen=False).starten()
        self.assertEqual("abgebrochen", lauf.warten())
        self.assertEqual([2], lauf.fragen)
        self.assertEqual(0, self.konsole.zaehle("SETID") + self.konsole.zaehle("FAKESIGNIN"))
        self.assertEqual("rpassist.jetzt_abgebrochen", lauf.letzte_anweisung().text)

    def test_ohne_payload_nennt_er_den_download(self) -> None:
        lauf = self._lauf(agent_elf="").starten()
        self.assertEqual("fehler", lauf.warten())
        letzte = lauf.letzte_anweisung()
        self.assertEqual("rpassist.jetzt_kein_payload", letzte.text)
        self.assertEqual(ADRESSE, letzte.werte["adresse"])
        self.assertEqual("actremotelink_agent*.elf", letzte.werte["datei"])
        self._texte_passen(lauf)

    def test_ohne_pin_payload_nennt_er_den_download(self) -> None:
        k = self.konsole
        k.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)
        lauf = self._lauf(pin_elf="").starten()
        self.assertEqual("fehler", lauf.warten())
        self.assertEqual("actremotelink_pin_notify*.elf",
                         lauf.letzte_anweisung().werte["datei"])


class WartenTests(_MitKonsole):
    """Wo nur der Anwender weiterkommt, wartet der Assistent - und sieht selbst,
    wann es weitergeht."""

    def test_neuer_benutzer_wird_erkannt(self) -> None:
        k = self.konsole
        del k.benutzer[2]
        k.vorn = 1
        lauf = self._lauf().starten()
        lauf.wartet_auf("rpassist.jetzt_neuer_benutzer")
        self.assertEqual(0, k.zaehle("SETID"))
        with k.schloss:
            k.benutzer[2] = _frisch("Neu", 0x10000001)
            k.vorn = 2
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertEqual(1, k.zaehle("SETID 2 "))
        self._texte_passen(lauf)

    def test_bei_mehreren_zaehlt_der_vorne(self) -> None:
        k = self.konsole
        k.benutzer[3] = _frisch("Zweiter", 0x10000002)
        k.vorn = 1
        lauf = self._lauf().starten()
        wartet = lauf.wartet_auf("rpassist.jetzt_waehlen")
        self.assertIn("Stream (2)", wartet.werte["namen"])
        self.assertIn("Zweiter (3)", wartet.werte["namen"])
        with k.schloss:
            k.vorn = 3
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertEqual(1, k.zaehle("SETID 3 "))
        self.assertEqual(0, k.zaehle("SETID 2 "))
        self._texte_passen(lauf)

    def test_die_anmeldung_wartet_auf_den_vordergrund(self) -> None:
        k = self.konsole
        k.vorn = 1
        lauf = self._lauf(slot=2).starten()
        wartet = lauf.wartet_auf("rpassist.jetzt_wechseln")
        self.assertEqual("anmeldung", wartet.schritt)
        self.assertEqual(1, k.zaehle("SETID 2 "), "SETID braucht keinen Vordergrund.")
        self.assertEqual(0, k.zaehle("FAKESIGNIN"))
        with k.schloss:
            k.vorn = 2
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertEqual(1, k.zaehle("FAKESIGNIN 2"))

    def test_konsole_zuerst_nicht_erreichbar(self) -> None:
        lauf = self._lauf(lader=[False]).starten()
        lauf.wartet_auf("rpassist.jetzt_lader")
        self.assertEqual([], self.konsole.gesendet)
        lauf.lader[0] = True
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertEqual([Path(AGENT_ELF).name], self.konsole.gesendet)

    def test_abbrechen_beim_warten(self) -> None:
        k = self.konsole
        del k.benutzer[2]
        k.vorn = 1
        lauf = self._lauf().starten()
        lauf.wartet_auf("rpassist.jetzt_neuer_benutzer")
        beginn = time.monotonic()
        lauf.abbrechen = True
        self.assertEqual("abgebrochen", lauf.warten(5.0))
        self.assertLess(time.monotonic() - beginn, 2.0)

    def test_neustart_aus_frueherem_lauf_agent_lebt_noch(self) -> None:
        """Der Agent ueberlebt keinen Neustart - lebt er, steht er noch aus."""
        k = self.konsole
        k.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)
        k.agent_an = True
        lauf = self._lauf(neustart_offen=True, pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertEqual(0, k.zaehle("PREPARE_PIN"))
        k.neustart()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(0, k.zaehle("SETID") + k.zaehle("FAKESIGNIN"))

    def test_neustart_aus_frueherem_lauf_ist_erfolgt(self) -> None:
        k = self.konsole
        k.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)
        lauf = self._lauf(neustart_offen=True, pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual([False], [e.werte["neustart_offen"]
                                   for e in lauf.ereignisse if e.art == "merken"])
        self.assertFalse(any(e.text == "rpassist.jetzt_neustart" for e in lauf.ereignisse))

    def test_kurz_weg_ist_kein_neustart(self) -> None:
        """Antwortet der alte Agent wieder, ohne dass er geschickt wurde, war
        die PS5 nur kurz nicht erreichbar - weiter auf den Neustart warten."""
        k = self.konsole
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        lauf.wartet_auf("rpassist.jetzt_neustart")
        lauf.lader[0] = False
        k.neustart()
        lauf.warten_auf(lambda e: e.art == "protokoll"
                        and e.text == "rpassist.log_neustart_erkannt")
        with k.schloss:
            k.agent_an = True           # derselbe Agent - niemand hat ihn geschickt
        lauf.warten_auf(lambda e: e.art == "protokoll"
                        and e.text == "rpassist.log_doch_kein_neustart")
        self.assertEqual(1, k.gesendet.count(Path(AGENT_ELF).name))
        lauf.lader[0] = True
        k.neustart()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(2, k.gesendet.count(Path(AGENT_ELF).name))
        self._texte_passen(lauf)

    def test_anmeldung_ueberlebt_den_neustart_nicht(self) -> None:
        k = self.konsole
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        lauf.wartet_auf("rpassist.jetzt_neustart")
        k.neustart(anmeldung_vergessen=True)
        lauf.warten_auf(lambda e: e.art == "protokoll"
                        and e.text == "rpassist.log_anmeldung_fehlt_noch")

        def _zweites_warten(_e) -> bool:
            return sum(1 for x in list(lauf.ereignisse)
                       if x.art == "schritt" and x.zustand == ra.WARTET
                       and x.text == "rpassist.jetzt_neustart") >= 2

        lauf.warten_auf(_zweites_warten)
        k.neustart()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(2, k.zaehle("FAKESIGNIN 2"))
        self.assertEqual(1, k.zaehle("SETID"), "Die account_id stand ja schon.")

    def test_nur_die_anmeldung_fehlt_auch_dann_ein_neustart(self) -> None:
        """account_id steht schon (etwa von SETID eines frueheren Laufs), die
        Anmeldung fehlt: nach FAKESIGNIN trotzdem erst neu starten."""
        k = self.konsole
        k.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)
        k.benutzer[2]["signin"] = ""
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        lauf.wartet_auf("rpassist.jetzt_neustart")
        self.assertEqual(0, k.zaehle("SETID"))
        self.assertEqual(1, k.zaehle("FAKESIGNIN 2"))
        self.assertEqual(0, k.zaehle("PREPARE_PIN"), "PIN vor dem Neustart")
        k.neustart()
        self.assertEqual("gekoppelt", lauf.warten())

    def test_alter_agent_ohne_signin_feld(self) -> None:
        k = self.konsole
        k.signin_feld = False
        k.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(0, k.zaehle("FAKESIGNIN"))


class PinTests(_MitKonsole):
    """PIN erzeugen und auf Chiaki warten."""

    def setUp(self) -> None:
        super().setUp()
        self.konsole.benutzer[2] = _fertig("Stream", 0x10000001, 0x499602D2)

    def _folge(self, *leser):
        folge = iter(leser)
        return lambda _pfad: next(folge)

    def test_die_pin_wartet_auf_den_vordergrund(self) -> None:
        """Das PIN-Payload nimmt den Benutzer, der vorne ist - also erst,
        wenn es der richtige ist."""
        k = self.konsole
        k.vorn = 1
        lauf = self._lauf(slot=2, pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING SUCCESS\n")).starten()
        wartet = lauf.wartet_auf("rpassist.jetzt_wechseln")
        self.assertEqual("pin", wartet.schritt)
        self.assertEqual(0, k.zaehle("PREPARE_PIN"))
        with k.schloss:
            k.vorn = 2
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(1, k.zaehle("PREPARE_PIN"))

    def test_abgelaufene_pin_wird_ersetzt(self) -> None:
        lauf = self._lauf(pin_mitlesen=self._folge(
            _Leser(PIN_AUSGABE),                       # endet ohne Ergebnis
            _Leser(ZWEITE_PIN, "PAIRING SUCCESS\n"))).starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(2, self.konsole.zaehle("PREPARE_PIN"))
        self.assertTrue(lauf.protokolliert("rpassist.log_neue_pin_abgelaufen"))
        pins = [e.werte["pin"] for e in lauf.ereignisse if e.art == "pin" and e.werte["pin"]]
        self.assertEqual(["2836 0549", "1111 2222"], pins)
        self._texte_passen(lauf)

    def test_falsche_pin_und_falsche_konto_id(self) -> None:
        lauf = self._lauf(pin_mitlesen=self._folge(
            _Leser(PIN_AUSGABE, "PAIRING FAILED invalid_pin\n"),
            _Leser(PIN_AUSGABE, "PAIRING FAILED invalid_account_id\n"),
            _Leser(ZWEITE_PIN, "PAIRING SUCCESS\n"))).starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertTrue(lauf.protokolliert("rpassist.log_neue_pin_falsche_pin"))
        self.assertTrue(lauf.protokolliert("rpassist.log_neue_pin_falsche_konto_id"))
        self._texte_passen(lauf)

    def test_nach_drei_pins_gibt_er_auf(self) -> None:
        lauf = self._lauf(pin_mitlesen=self._folge(
            _Leser(PIN_AUSGABE), _Leser(PIN_AUSGABE), _Leser(PIN_AUSGABE))).starten()
        self.assertEqual("fehler", lauf.warten())
        self.assertEqual("rpassist.jetzt_pin_aufgegeben", lauf.letzte_anweisung().text)
        self.assertEqual(ra.PIN_VERSUCHE, self.konsole.zaehle("PREPARE_PIN"))
        self._texte_passen(lauf)

    def test_anderer_kopplungsfehler(self) -> None:
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            PIN_AUSGABE, "PAIRING FAILED 0x80fc1234\n")).starten()
        self.assertEqual("fehler", lauf.warten())
        letzte = lauf.letzte_anweisung()
        self.assertEqual("rpassist.jetzt_pin_fehler", letzte.text)
        self.assertEqual("0x80fc1234", letzte.werte["text"])

    def test_payload_endet_ohne_pin(self) -> None:
        lauf = self._lauf(pin_mitlesen=lambda _p: _Leser(
            "ActRemoteLink: initializing Remote Play...\n")).starten()
        self.assertEqual("fehler", lauf.warten())
        self.assertEqual("rpassist.jetzt_pin_beendet", lauf.letzte_anweisung().text)

    def test_ohne_ausgabe_erkennt_er_die_kopplung_an_paired(self) -> None:
        """Der Payload Manager reicht keine Ausgabe zurueck - dann zeigt die
        Konsole selbst, ob Chiaki gekoppelt hat."""
        k = self.konsole
        k.koppeln_nach_fragen = 3
        lauf = self._lauf(pin_mitlesen=lambda _p: None).starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertIn(Path(PIN_ELF).name, k.gesendet)
        self.assertTrue(lauf.protokolliert("rpassist.log_pin_ohne_ausgabe"))
        pin = [e.werte for e in lauf.ereignisse if e.art == "pin"][-1]
        self.assertEqual("", pin["pin"])
        self.assertEqual(_b64(0x499602D2), pin["b64"],
                         "Die Konto-ID kommt aus PREPARE_PIN - auch ohne Ausgabe.")

    def test_ohne_ausgabe_laeuft_die_pin_ab(self) -> None:
        lauf = self._lauf(pin_mitlesen=lambda _p: None, pin_gueltig=0.3).starten()
        self.assertEqual("fehler", lauf.warten())
        self.assertEqual("rpassist.jetzt_pin_aufgegeben", lauf.letzte_anweisung().text)
        self.assertEqual(ra.PIN_VERSUCHE,
                         self.konsole.gesendet.count(Path(PIN_ELF).name))

    def test_leser_wird_immer_geschlossen(self) -> None:
        leser = _Leser(PIN_AUSGABE, *([None] * 1000))
        lauf = self._lauf(pin_mitlesen=lambda _p: leser)
        lauf.starten()
        lauf.warten_auf(lambda e: e.art == "pin" and e.werte["pin"])
        lauf.abbrechen = True
        self.assertEqual("abgebrochen", lauf.warten())
        self.assertTrue(leser.geschlossen)

    def test_pin_ueber_den_echten_mitleser(self) -> None:
        stube = _LaderStube(PIN_AUSGABE, "PAIRING SUCCESS\n")
        self.addCleanup(stube.schliessen)
        lauf = self._lauf(pin_mitlesen=lambda _p: payload_versand.Mitleser(
            "127.0.0.1", b"\x7fELF-pin", port=stube.port, takt=0.1)).starten()
        self.assertEqual("gekoppelt", lauf.warten())
        self.assertEqual(b"\x7fELF-pin", stube.empfangen)
        self.assertEqual("2836 0549", [e.werte["pin"] for e in lauf.ereignisse
                                       if e.art == "pin"][-1])


class TexteTests(unittest.TestCase):
    """Jeder Schluessel, den der Assistent meldet, steht in beiden Sprachen."""

    def test_alle_schluessel_des_moduls(self) -> None:
        quelle = Path(ra.__file__).read_text(encoding="utf-8")
        schluessel = set(re.findall(r'"(rpassist\.[a-z_]+)"', quelle))
        schluessel.discard("rpassist.log_neue_pin_")
        schluessel |= {"rpassist.log_neue_pin_" + grund for grund in
                       ("abgelaufen", "falsche_pin", "falsche_konto_id")}
        self.assertGreater(len(schluessel), 30)
        for k in sorted(schluessel):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=k, sprache=sprache):
                    self.assertTrue(STRINGS.get(k, {}).get(sprache))

    def test_alle_schluessel_der_oberflaeche(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        schluessel = set(re.findall(r'"(rpassist\.[a-z_]+)"', quelle))
        # Zusammengesetzt: "rpassist.schritt_" + Schritt usw.
        schluessel -= {"rpassist.schritt_", "rpassist.wer_"}
        schluessel |= {"rpassist.schritt_" + s for s in ra.ASSISTENT_SCHRITTE}
        schluessel |= {"rpassist.wer_" + s for s in ra.ASSISTENT_SCHRITTE}
        schluessel.add("konsole.btn_actremotelink")
        for k in sorted(schluessel):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=k, sprache=sprache):
                    self.assertTrue(STRINGS.get(k, {}).get(sprache))

    def test_die_reihenfolge_nennt_die_payloads(self) -> None:
        """Welches ELF wann geschickt wird, steht am Schritt selbst."""
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertIn("actremotelink_agent.elf",
                              STRINGS["rpassist.wer_verbinden"][sprache])
                self.assertIn("actremotelink_pin_notify.elf",
                              STRINGS["rpassist.wer_pin"][sprache])
        self.assertLess(ra.ASSISTENT_SCHRITTE.index("verbinden"),
                        ra.ASSISTENT_SCHRITTE.index("konto"))
        self.assertLess(ra.ASSISTENT_SCHRITTE.index("anmeldung"),
                        ra.ASSISTENT_SCHRITTE.index("neustart"))
        self.assertLess(ra.ASSISTENT_SCHRITTE.index("neustart"),
                        ra.ASSISTENT_SCHRITTE.index("pin"))

    def test_der_alte_einzelschritt_ist_weg(self) -> None:
        """Bis zum 24.09.2026 machte "Koppeln" je Druck einen Schritt und
        verlangte zwei Neustarts. Der Assistent ersetzt ihn ganz."""
        self.assertFalse(hasattr(ra.ActRemoteLink, "koppeln"))
        self.assertFalse(hasattr(ra, "Kopplungsstand"))
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        aufrufe = [k.lineno for k in ast.walk(baum) if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "koppeln"]
        self.assertEqual([], aufrufe)


# ---------------------------------------------------------------- Oberflaeche

def _schleife_bis(bedingung, grenze: float = 15.0) -> bool:
    """Echte Hauptschleife mit selbst endendem Takt."""
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(20, _takt)
    _WURZEL.mainloop()
    return bool(bedingung())


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


def _klick(widget) -> None:
    """Ruft die Bindung von <Button-1> auf.

    ``event generate`` kommt im Hauptfenster nicht an - es ist im Test
    ausgeblendet. Die Bindung ist ein Tcl-Befehl, der die Ereignisfelder als
    Argumente erwartet (wie ``_doppelklick`` in test_konsole_stufe4).
    """
    skript = widget.bind("<Button-1>")
    befehl = re.search(r"\[(\S+)", skript).group(1)
    widget.tk.call(befehl, *(["0"] * len(widget._subst_format)))


def _sichtbar(widget) -> bool:
    if widget is None:
        return False
    try:
        return widget.winfo_manager() == "grid" and bool(widget.grid_info())
    except tk.TclError:
        return False


class _FalscherAssistent:
    """Statt des echten: meldet einen vorbereiteten Ablauf."""

    zuletzt: "dict | None" = None
    folge: list = []
    ergebnis = "gekoppelt"

    def __init__(self, agent, **optionen) -> None:
        type(self).zuletzt = dict(optionen, agent=agent)
        self.melden = optionen["melden"]

    def lauf(self) -> str:
        for ereignis in type(self).folge:
            self.melden(ereignis)
            time.sleep(0.01)
        return type(self).ergebnis


def _erste_ansicht_merken(app) -> None:
    """Die gemerkte Ansicht auf "umwandeln".

    Jedes Programmfenster stellt beim Start die gemerkte Ansicht wieder her -
    verzoegert, nach der Startphase. Stand dort "konsole", baute es mitten in
    einem spaeteren Test die Tafel als neues Kind der Wurzel; Pruefungen, die
    "das neue Fenster" als letztes Kind suchen, griffen daneben (gemessen am
    24.09.2026: test_doppelklick_auf_einen_benutzer_setzt_den_slot kippte
    zufaellig).
    """
    app._konfiguration_schreiben({"ansicht": "umwandeln"})


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeiteTests(unittest.TestCase):
    """Rechts in der Ansicht KONSOLE, hinter "6. ActRemoteLink"."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _erste_ansicht_merken(cls.app)
        _WURZEL.update_idletasks()

    @classmethod
    def tearDownClass(cls) -> None:
        _erste_ansicht_merken(cls.app)

    def tearDown(self) -> None:
        st = getattr(self.app, "_rpassist", None)
        if st is not None and st["laeuft"]:
            st["abbrechen"] = True
            _schleife_bis(lambda: not st["laeuft"], 5.0)
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()

    def _knopf(self):
        for knopf, schluessel in self.app._konsole_knoepfe:
            if schluessel == "konsole.btn_actremotelink":
                return knopf
        self.fail("Der Knopf ActRemoteLink fehlt.")

    def _seite_zeigen(self):
        """Zeigt die Seite - im Ausgangszustand, gleich was ein Test davor tat."""
        self.app._ansicht_setzen("konsole", speichern=False)
        self.app._konsole_seite_setzen("actremotelink")
        st = self.app._rpassist
        st.update(ergebnis="", pin=None,
                  jetzt=("rpassist.jetzt_bereit", {}, ra.OFFEN),
                  zustaende={s: ra.OFFEN for s in ra.ASSISTENT_SCHRITTE})
        st["status_var"].set(self.app._rpassist_statustext())
        self.app._rpassist_zeichnen()
        _WURZEL.update()
        return st

    def test_der_knopf_zeigt_rechts_den_assistenten(self) -> None:
        app = self.app
        app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        self.assertTrue(_sichtbar(app._konsole_tafel))
        # RoundedButton haelt Text und Farbe selbst (_text/_bg), nicht im Canvas.
        self.assertEqual(app._t("konsole.btn_actremotelink"), self._knopf()._text)
        self._knopf()._on_click()
        _WURZEL.update()
        seite = app._rpassist_seite
        self.assertTrue(_sichtbar(seite))
        self.assertFalse(_sichtbar(app._konsole_tafel))
        self.assertFalse(_sichtbar(app.content_scroll))
        lage = seite.grid_info()
        self.assertEqual((1, 1), (int(lage["row"]), int(lage["column"])))
        self.assertEqual(app._COLORS["fg_accent"], self._knopf()._bg,
                         "Der Knopf der gezeigten Seite ist hervorgehoben.")
        self._knopf()._on_click()
        _WURZEL.update()
        self.assertFalse(_sichtbar(seite))
        self.assertTrue(_sichtbar(app._konsole_tafel))
        self.assertEqual(app._COLORS["bg_card"], self._knopf()._bg)

    def test_die_uebersicht_hat_einen_rueckweg(self) -> None:
        st = self._seite_zeigen()
        zurueck = [w for w in _alle(self.app._rpassist_seite)
                   if _text(w) == self.app._t("rpassist.btn_uebersicht")]
        self.assertEqual(1, len(zurueck))
        zurueck[0].invoke()
        _WURZEL.update()
        self.assertTrue(_sichtbar(self.app._konsole_tafel))
        self.assertFalse(_sichtbar(self.app._rpassist_seite))
        self.assertIsNotNone(st)

    def test_die_wahl_ueberdauert_das_umschalten(self) -> None:
        app = self.app
        self._seite_zeigen()
        app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()
        self.assertFalse(_sichtbar(app._rpassist_seite))
        self.assertTrue(_sichtbar(app.content_scroll))
        app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        self.assertTrue(_sichtbar(app._rpassist_seite))
        self.assertFalse(_sichtbar(app._konsole_tafel))

    def test_der_ablauf_steht_in_seiner_reihenfolge_da(self) -> None:
        st = self._seite_zeigen()
        titel = [st["zeilen"][s][1].cget("text") for s in ra.ASSISTENT_SCHRITTE]
        self.assertEqual(["1. Verbindung und Agent", "2. Benutzer wählen",
                          "3. account_id setzen", "4. Offline-Anmeldung",
                          "5. PS5 neu starten", "6. PIN erzeugen",
                          "7. In Chiaki koppeln"], titel)
        self.assertIn("actremotelink_agent.elf",
                      st["zeilen"]["verbinden"][2].cget("text"))
        self.assertIn("actremotelink_pin_notify.elf",
                      st["zeilen"]["pin"][2].cget("text"))
        self.assertEqual({"○"}, {st["zeilen"][s][0].cget("text")
                                  for s in ra.ASSISTENT_SCHRITTE})
        self.assertEqual(self.app._t("rpassist.jetzt_bereit"),
                         st["jetzt_label"].cget("text"))

    def test_die_seite_passt_in_die_kleinste_fensterhoehe(self) -> None:
        """Am 24.09.2026 bei 1245x700 und 125 % aufgenommen: Der letzte
        Schritt, das Protokoll und die Statuszeile fielen aus dem Fenster,
        die PIN war auf "28" gekuerzt. Gemessen wird die angeforderte Hoehe
        ohne das Protokoll (das schrumpft mit Absicht), umgerechnet auf die
        Skalierung, bei der gemessen wurde (125 % = 120 dpi)."""
        st = self._seite_zeigen()
        for schritt in ra.ASSISTENT_SCHRITTE:
            st["zustaende"][schritt] = ra.ERLEDIGT
        st["jetzt"] = ("rpassist.jetzt_chiaki", {"adresse": "10.0.0.5"}, ra.WARTET)
        st["pin"] = {"pin": "2836 0549", "b64": "eGlaSzwtHo8=",
                     "bis": time.monotonic() + 200}
        self.addCleanup(st.update, pin=None, jetzt=("rpassist.jetzt_bereit", {}, ra.OFFEN),
                        zustaende={s: ra.OFFEN for s in ra.ASSISTENT_SCHRITTE})
        self.app._rpassist_zeichnen()
        _WURZEL.update_idletasks()
        seite = self.app._rpassist_seite
        ohne_protokoll = seite.winfo_reqheight() - st["protokoll"].winfo_reqheight()
        punkt = float(_WURZEL.tk.call("tk", "scaling"))     # Pixel je Punkt
        bei_125 = ohne_protokoll * (120.0 / 72.0) / punkt
        self.assertLessEqual(bei_125, APP.WINDOW_MIN_HEIGHT,
                             "Seite braucht %.0f px (bei 125 %%), das Fenster hat "
                             "mindestens %d" % (bei_125, APP.WINDOW_MIN_HEIGHT))
        # Die PIN-Karte steht unter "Jetzt", die PIN in eigener Zeile.
        self.assertEqual("2836 0549", st["pin_wert"].cget("text"))
        self.assertEqual(1, int(st["pin_wert"].grid_info()["row"]))

    def test_die_seite_folgt_dem_sprachwechsel(self) -> None:
        st = self._seite_zeigen()
        with mock.patch.object(self.app, "_save_setting", lambda *_a: None):
            self.app._toggle_language()
            try:
                self.assertEqual("en", self.app._current_language)
                self.assertEqual("1. Connection and agent",
                                 st["zeilen"]["verbinden"][1].cget("text"))
                self.assertEqual(STRINGS["rpassist.jetzt_bereit"]["en"],
                                 st["jetzt_label"].cget("text"))
                self.assertEqual("Ready.", st["status_var"].get())
                self.assertEqual("Start", st["start_btn"].cget("text"))
            finally:
                self.app._toggle_language()
        self.assertEqual("1. Verbindung und Agent",
                         st["zeilen"]["verbinden"][1].cget("text"))

    def test_umschalten_startet_nichts(self) -> None:
        vorher = {t.name for t in threading.enumerate()}
        self._seite_zeigen()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertFalse({n for n in neu if n.startswith("rpassist")})

    def _starten(self, folge, ergebnis="gekoppelt", ip="10.0.0.5",
                 slot="", konto=""):
        st = self._seite_zeigen()
        st["ip_var"].set(ip)
        st["slot_var"].set(slot)
        st["konto_var"].set(konto)
        _FalscherAssistent.folge = folge
        _FalscherAssistent.ergebnis = ergebnis
        _FalscherAssistent.zuletzt = None
        gespeichert: list = []
        with mock.patch.object(APP.remoteplay_agent, "Kopplungsassistent",
                               _FalscherAssistent), \
                mock.patch.object(self.app, "_save_setting",
                                  lambda k, v: gespeichert.append((k, v))):
            st["start_btn"].invoke()
            # Fertig ist es erst, wenn der letzte Takt den Endstand gezeichnet
            # hat - das Ende des Fadens allein reicht nicht.
            laufend = self.app._t("rpassist.status_laeuft")
            self.assertTrue(_schleife_bis(
                lambda: not st["laeuft"] and st["status_var"].get() != laufend))
            _WURZEL.update()
        return st, gespeichert

    def test_ein_lauf_zeigt_schritte_pin_und_ende(self) -> None:
        E = ra.Ereignis
        folge = [
            E("schritt", "verbinden", ra.LAEUFT, "rpassist.jetzt_verbinden",
              {"adresse": "10.0.0.5"}),
            E("schritt", "verbinden", ra.ERLEDIGT, ""),
            E("merken", werte={"neustart_offen": True}),
            E("merken", werte={"neustart_offen": False}),
            E("schritt", "neustart", ra.UEBERSPRUNGEN, ""),
            E("pin", werte={"pin": "2836 0549", "b64": "eGlaSzwtHo8=",
                            "bis": time.monotonic() + 300}),
            E("ausgabe", text="OK PIN"),
            E("protokoll", text="rpassist.log_gekoppelt", werte={"slot": 2}),
            E("schritt", "chiaki", ra.ERLEDIGT, "rpassist.jetzt_fertig",
              {"name": "Stream", "slot": 2}),
        ]
        st, gespeichert = self._starten(folge)
        self.assertEqual("2836 0549", st["pin_wert"].cget("text"))
        self.assertEqual("eGlaSzwtHo8=", st["id_wert"].cget("text"))
        self.assertEqual("✓", st["zeilen"]["chiaki"][0].cget("text"))
        self.assertEqual("✓", st["zeilen"]["verbinden"][0].cget("text"))
        self.assertEqual("–", st["zeilen"]["neustart"][0].cget("text"))
        self.assertEqual(self.app._t("rpassist.jetzt_fertig", name="Stream", slot=2),
                         st["jetzt_label"].cget("text"))
        self.assertEqual(self.app._t("rpassist.status_gekoppelt"),
                         st["status_var"].get())
        protokoll = st["protokoll"].get("1.0", "end")
        self.assertIn("[PS5] OK PIN", protokoll)
        self.assertIn(self.app._t("rpassist.log_gekoppelt", slot=2), protokoll)
        self.assertIn(("remoteplay_neustart_offen", "10.0.0.5"), gespeichert)
        self.assertIn(("remoteplay_neustart_offen", ""), gespeichert)
        self.assertEqual("normal", str(st["start_btn"].cget("state")))
        self.assertEqual("disabled", str(st["stop_btn"].cget("state")))

        self.app._rpassist_kopieren("pin")
        self.assertEqual("28360549", _WURZEL.clipboard_get(),
                         "Chiaki nimmt die PIN ohne Leerzeichen.")
        self.app._rpassist_kopieren("b64")
        self.assertEqual("eGlaSzwtHo8=", _WURZEL.clipboard_get())

    def test_die_eingaben_gehen_an_den_assistenten(self) -> None:
        self.app._konfiguration_schreiben({"remoteplay_neustart_offen": "10.0.0.5"})
        self.addCleanup(self.app._konfiguration_schreiben,
                        {"remoteplay_neustart_offen": ""})
        self._starten([], slot="3", konto="1234567890")
        optionen = _FalscherAssistent.zuletzt
        self.assertEqual("3", optionen["slot"])
        self.assertEqual("1234567890", optionen["konto_id"])
        self.assertTrue(optionen["neustart_offen"])
        agent = optionen["agent"]
        self.assertEqual("10.0.0.5", agent.host)
        # Die Rueckfrage vor dem ersten Schreiben - aus dem Hauptfaden direkt.
        from tkinter import messagebox
        with mock.patch.object(messagebox, "askyesno", return_value=True) as frage:
            self.assertTrue(optionen["bestaetigen"](ra.Benutzer(slot=2, name="Stream")))
        self.assertIn("Slot 2", frage.call_args[0][1])
        self.assertIn("Stream", frage.call_args[0][1])
        # Der Agent schreibt nichts und laeuft dauerhaft: kurze Lesezeit.
        gesendet: list = []
        with mock.patch.object(self.app, "_send_payload_to_ps5",
                               lambda *a, **k: gesendet.append((a, k)) or (True, "")):
            agent.sende_payload(AGENT_ELF)
        self.assertEqual([(("10.0.0.5", AGENT_ELF), {"lesezeit": 5.0})], gesendet)

    def test_die_lesezeit_geht_an_den_versand(self) -> None:
        """``_send_payload_to_ps5(lesezeit=)`` kommt als ``timeout`` bei
        ``payload_versand.senden`` an - sonst wartete jeder Agentstart 30 s."""
        aufrufe: list = []

        def _senden(*argumente, **benannt):
            aufrufe.append(benannt)
            return payload_versand.WEG_ELFLDR, "", ""

        ordner = tempfile.TemporaryDirectory()
        self.addCleanup(ordner.cleanup)
        elf = Path(ordner.name) / "agent.elf"
        elf.write_bytes(b"\x7fELF")
        with mock.patch.object(APP.payload_versand, "senden", _senden):
            self.assertTrue(self.app._send_payload_to_ps5("10.0.0.5", str(elf),
                                                          lesezeit=5.0)[0])
            self.app._send_payload_to_ps5("10.0.0.5", str(elf))
        self.assertEqual([5.0, 30.0], [a["timeout"] for a in aufrufe])

    def test_leere_felder_und_falsche_eingaben(self) -> None:
        from tkinter import messagebox
        st = self._seite_zeigen()
        st["ip_var"].set("")
        st["start_btn"].invoke()
        self.assertFalse(st["laeuft"])
        self.assertEqual(self.app._t("dienste.need_ip"), st["status_var"].get())
        st["ip_var"].set("10.0.0.5")
        for slot, konto in (("x", ""), ("", "abc"), ("", "0")):
            st["slot_var"].set(slot)
            st["konto_var"].set(konto)
            with self.subTest(slot=slot, konto=konto), \
                    mock.patch.object(messagebox, "showwarning") as warnung:
                st["start_btn"].invoke()
                self.assertFalse(st["laeuft"])
                warnung.assert_called_once()

    def test_ein_link_in_jetzt_oeffnet_die_adresse(self) -> None:
        st = self._seite_zeigen()
        st["jetzt"] = ("rpassist.jetzt_kein_payload",
                       {"datei": "actremotelink_agent*.elf", "adresse": ADRESSE},
                       ra.FEHLER)
        self.app._rpassist_zeichnen()
        self.assertIn(ADRESSE, st["jetzt_label"].cget("text"))
        self.assertEqual("hand2", str(st["jetzt_label"].cget("cursor")))
        geoeffnet: list = []
        with mock.patch.object(self.app, "_open_url", geoeffnet.append):
            self.app._rpassist_link_oeffnen()
        self.assertEqual([ADRESSE], geoeffnet)
        st["jetzt"] = ("rpassist.jetzt_lader", {"adresse": "10.0.0.5"}, ra.WARTET)
        self.app._rpassist_zeichnen()
        self.assertEqual("", str(st["jetzt_label"].cget("cursor")),
                         "Eine IP ist kein Link.")

    def test_fehlt_ein_payload_steht_die_adresse_auf_der_seite(self) -> None:
        app = self.app
        alt = getattr(app, "_rpassist_seite", None)
        altes_st = getattr(app, "_rpassist", None)
        with mock.patch.object(app, "_streaming_pfad", lambda _art: ""):
            app._konsole_assistent_bauen()
        try:
            hinweise = [w for w in _alle(app._rpassist_seite) if ADRESSE in _text(w)]
            self.assertEqual(1, len(hinweise))
            self.assertEqual("hand2", str(hinweise[0].cget("cursor")))
            geoeffnet: list = []
            with mock.patch.object(app, "_open_url", geoeffnet.append):
                _klick(hinweise[0])
            self.assertEqual([ADRESSE], geoeffnet)
        finally:
            app._rpassist_seite.destroy()
            app._rpassist_seite, app._rpassist = alt, altes_st


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class RemotePlayFensterTests(unittest.TestCase):
    """Das Fenster Remote Play: Download-Hinweis und Weg zum Assistenten."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _erste_ansicht_merken(cls.app)
        _WURZEL.update_idletasks()

    @classmethod
    def tearDownClass(cls) -> None:
        _erste_ansicht_merken(cls.app)

    def tearDown(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()

    def _oeffnen(self, fehlend: set):
        echt = self.app._streaming_pfad

        def _pfad(art: str) -> str:
            return "" if art in fehlend else (echt(art) or "C:/x/%s.elf" % art)

        vorher = set(_WURZEL.winfo_children())
        with mock.patch.object(self.app, "_streaming_pfad", _pfad):
            self.app._show_konsole_remoteplay()
        _WURZEL.update()
        fenster = [w for w in _WURZEL.winfo_children() if w not in vorher
                   and isinstance(w, tk.Toplevel)][-1]
        self.addCleanup(lambda: fenster.winfo_exists() and fenster.destroy())
        return fenster

    def test_fehlt_ein_payload_steht_die_adresse_da(self) -> None:
        for fehlend in ({"agent"}, {"pin"}, {"agent", "pin"}):
            with self.subTest(fehlend=sorted(fehlend)):
                fenster = self._oeffnen(fehlend)
                hinweise = [w for w in _alle(fenster) if ADRESSE in _text(w)]
                self.assertEqual(1, len(hinweise), "Die Download-Adresse fehlt.")
                for art in fehlend:
                    self.assertIn(ra.PAYLOAD_MUSTER[art], _text(hinweise[0]))
                geoeffnet: list = []
                with mock.patch.object(self.app, "_open_url", geoeffnet.append):
                    hinweise[0].event_generate("<Button-1>")
                    _WURZEL.update()
                self.assertEqual([ADRESSE], geoeffnet)
                protokoll = [w for w in _alle(fenster) if isinstance(w, tk.Text)][0]
                self.assertIn(ADRESSE, protokoll.get("1.0", "end"))

    def test_liegen_beide_bei_steht_kein_hinweis_da(self) -> None:
        fenster = self._oeffnen(set())
        self.assertEqual([], [w for w in _alle(fenster) if ADRESSE in _text(w)])

    def test_benutzer_lesen_merkt_den_erfolgten_neustart(self) -> None:
        """Musste "Benutzer lesen" den Agenten neu schicken, lebte der alte
        nicht mehr - ein Neustart, auf den der Assistent wartete, ist durch."""
        from tkinter import ttk
        fenster = self._oeffnen(set())
        gespeichert: list = []
        with mock.patch.object(self.app, "_streaming_pfad",
                               lambda art: "C:/x/%s.elf" % art), \
                mock.patch.object(ra.ActRemoteLink, "laeuft", return_value=False), \
                mock.patch.object(ra.ActRemoteLink, "starten", return_value=True), \
                mock.patch.object(ra.ActRemoteLink, "benutzer_liste", return_value=[]), \
                mock.patch.object(self.app, "_save_setting",
                                  lambda k, v: gespeichert.append((k, v))):
            eintraege = [w for w in _alle(fenster) if isinstance(w, tk.Entry)]
            eintraege[0].delete(0, "end")
            eintraege[0].insert(0, "10.0.0.5")
            knopf = [w for w in _alle(fenster) if isinstance(w, ttk.Button)
                     and _text(w) == self.app._t("remoteplay.btn_users")][0]
            knopf.invoke()
            self.assertTrue(_schleife_bis(
                lambda: ("remoteplay_neustart_offen", "") in gespeichert, 10.0))

    def test_koppeln_fuehrt_zum_assistenten(self) -> None:
        from tkinter import ttk
        fenster = self._oeffnen(set())
        eintraege = [w for w in _alle(fenster) if isinstance(w, tk.Entry)]
        eintraege[0].delete(0, "end")
        eintraege[0].insert(0, "10.0.0.7")
        self.assertEqual("", eintraege[2].get(), "Slot leer = der vorne ist")
        eintraege[2].insert(0, "3")
        knopf = [w for w in _alle(fenster) if isinstance(w, ttk.Button)
                 and _text(w) == self.app._t("remoteplay.btn_link")][0]
        gespeichert: list = []
        with mock.patch.object(self.app, "_save_setting",
                               lambda k, v: gespeichert.append((k, v))):
            knopf.invoke()
            _WURZEL.update()
        # Wie beim Umschalten von Hand: Die Ansicht wird gemerkt.
        self.assertIn(("ansicht", "konsole"), gespeichert)
        self.assertTrue(self.app._ansicht_ist_konsole())
        self.assertTrue(_sichtbar(self.app._rpassist_seite))
        st = self.app._rpassist
        self.assertEqual("10.0.0.7", st["ip_var"].get())
        self.assertEqual("3", st["slot_var"].get())


if __name__ == "__main__":
    unittest.main(verbosity=2)
