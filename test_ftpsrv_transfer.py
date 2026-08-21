"""Regressionstests: ftpsrv als Übertragungsweg zur PS5 und die Rechteprüfung.

Vorgeschichte: Eine Zeit lang wurde der schnellere `zftpd` (Port 2120)
bevorzugt. Am 16.08.2026 fiel an der Konsole auf, dass er **jede** Datei mit
den Rechten 0666 anlegt – und die PS5 startet nichts, was nicht ausführbar ist.
Der Startversuch endet mit `CE-107750-0`, ohne jeden Hinweis auf die Ursache.
Nachgemessen: eine per zftpd hochgeladene Testdatei bekam `unix.mode=0666`,
während alle nachweislich startenden Einträge 0777 tragen. Heilen ließ sich das
über zftpd nicht – `SITE CHMOD` wird dort mit „200 successful" quittiert,
ändert aber nichts.

Seither gilt: **ftpsrv auf 2121 hat Vorrang**, zftpd steht am Ende der Suche,
und nach jedem Upload wird geprüft, ob die Datei ausführbar ist.

Geprüft wird die Entscheidungslogik ohne Netzwerk.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI, PS5_FTP_PORTS

HOST = "192.168.1.94"


class _Gui:
    """Baut ein Testobjekt mit steuerbaren Aussenkontakten."""

    def __init__(self, *, offene_ports: set[int], antwort: bool = True,
                 senden_klappt: bool = True, oeffnet_nach_senden: bool = True):
        self.gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        self.offene_ports = set(offene_ports)
        self.gefragt = 0
        self.gesendet = 0
        self.protokoll: list[str] = []

        def _port_offen(host, port, timeout=1.5):
            return int(port) in self.offene_ports

        def _fragen(_titel, _text, default_yes=True):
            self.gefragt += 1
            return antwort

        def _senden(host, pfad, port=0):
            self.gesendet += 1
            if senden_klappt and oeffnet_nach_senden:
                self.offene_ports.add(PS5ConverterGUI._FTPSRV_PORT)
            return (senden_klappt, "1 Byte" if senden_klappt else "Verbindung abgelehnt")

        self.gui._ps5_port_open = _port_offen
        self.gui._ask_yesno_threadsafe = _fragen
        self.gui._send_payload_to_ps5 = _senden
        self.gui._append_to_log = self.protokoll.append
        self.gui._t = lambda schluessel, **kw: schluessel
        self.gui._ftpsrv_payload_path = lambda: __file__     # existierende Datei genügt


class _Ftp:
    """Minimale FTP-Attrappe, die MLST und LIST beantworten kann."""

    def __init__(self, mlst: str | None = None, liste: list[str] | None = None):
        self._mlst = mlst
        self._liste = liste or []

    def sendcmd(self, befehl):
        if befehl.startswith("MLST") and self._mlst is not None:
            return "250-Listing\r\n " + self._mlst + "\r\n250 End"
        raise OSError("500 Unknown command")

    def retrlines(self, _befehl, callback):
        for zeile in self._liste:
            callback(zeile)


class FtpsrvWahlTests(unittest.TestCase):
    """Welcher Payload genommen und wann gefragt wird."""

    def test_laufender_ftpsrv_wird_ohne_rueckfrage_genutzt(self):
        h = _Gui(offene_ports={2120, 2121})
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 2121)
        self.assertEqual(h.gefragt, 0)
        self.assertEqual(h.gesendet, 0)

    def test_laufendes_zftpd_allein_genuegt_nicht(self):
        # Kernpunkt der Umstellung: zftpd darf ftpsrv nicht ersetzen.
        h = _Gui(offene_ports={2120}, antwort=False)
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 0)
        self.assertEqual(h.gefragt, 1, "es muss nach ftpsrv gefragt werden")

    def test_ohne_ftpsrv_wird_gefragt_und_gesendet(self):
        h = _Gui(offene_ports=set(), antwort=True)
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 2121)
        self.assertEqual(h.gefragt, 1)
        self.assertEqual(h.gesendet, 1)

    def test_ablehnung_wird_akzeptiert_und_nicht_wiederholt(self):
        h = _Gui(offene_ports=set(), antwort=False)
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 0)
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 0)   # zweiter Anlauf
        self.assertEqual(h.gefragt, 1, "es darf nur einmal je Sitzung gefragt werden")
        self.assertEqual(h.gesendet, 0)

    def test_fehlgeschlagener_versand_faellt_zurueck(self):
        h = _Gui(offene_ports=set(), antwort=True, senden_klappt=False)
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 0)
        self.assertEqual(h.gesendet, 1)
        self.assertTrue(any("send_failed" in z for z in h.protokoll))

    def test_payload_startet_nicht_dann_bleibt_der_alte_weg(self):
        h = _Gui(offene_ports=set(), antwort=True, oeffnet_nach_senden=False)
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 0)
        self.assertTrue(any("not_ready" in z for z in h.protokoll))

    def test_ohne_host_passiert_nichts(self):
        h = _Gui(offene_ports=set())
        self.assertEqual(h.gui._ensure_ftpsrv(""), 0)
        self.assertEqual(h.gefragt, 0)

    def test_fehlender_payload_fuehrt_nicht_zur_rueckfrage(self):
        h = _Gui(offene_ports=set())
        h.gui._ftpsrv_payload_path = lambda: ""
        self.assertEqual(h.gui._ensure_ftpsrv(HOST), 0)
        self.assertEqual(h.gefragt, 0)

    def test_der_mitgelieferte_payload_ist_vorhanden(self):
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        pfad = gui._ftpsrv_payload_path()
        self.assertTrue(pfad and Path(pfad).is_file(),
                        f"ftpsrv-Payload fehlt: {PS5ConverterGUI._FTPSRV_PAYLOAD_NAME}")


class PortreihenfolgeTests(unittest.TestCase):
    """2121 zuerst, 2120 zuletzt."""

    def test_ftpsrv_steht_vorn(self):
        self.assertEqual(PS5_FTP_PORTS[0], 2121)
        self.assertEqual(PS5ConverterGUI._FTPSRV_PORT, 2121)

    def test_zftpd_steht_ganz_hinten(self):
        # Er bleibt als letzter Notnagel erreichbar, wird aber nie bevorzugt.
        self.assertEqual(PS5_FTP_PORTS[-1], 2120)
        self.assertIn(2120, PS5_FTP_PORTS)

    def test_ftpsrv_kommt_vor_zftpd(self):
        self.assertLess(PS5_FTP_PORTS.index(2121), PS5_FTP_PORTS.index(2120))


class RechtepruefungTests(unittest.TestCase):
    """Die Warnung, die den stummen Fehlschlag künftig sichtbar macht."""

    def setUp(self):
        self.gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        self.protokoll: list[str] = []
        self.gui._append_to_log = self.protokoll.append
        self.gui._t = lambda schluessel, **kw: f"{schluessel} {kw}"

    def test_modus_aus_mlst(self):
        ftp = _Ftp(mlst="type=file;size=64;unix.mode=0666; /x/eboot.bin")
        self.assertEqual(self.gui._ps5_datei_modus(ftp, "/x/eboot.bin"), 0o666)

    def test_modus_aus_mlst_ohne_fuehrende_null(self):
        ftp = _Ftp(mlst="type=file;unix.mode=777; /x/eboot.bin")
        self.assertEqual(self.gui._ps5_datei_modus(ftp, "/x/eboot.bin"), 0o777)

    def test_modus_aus_list_wenn_mlst_fehlt(self):
        ftp = _Ftp(liste=["-rwxrwxrwx 1 ftp ftp 27702196 Aug 15 16:10 eboot.bin"])
        self.assertEqual(self.gui._ps5_datei_modus(ftp, "/x/eboot.bin"), 0o777)

    def test_modus_aus_list_ohne_ausfuehrungsrecht(self):
        ftp = _Ftp(liste=["-rw-rw-rw- 1 ftp ftp 37354809 Aug 16 09:21 eboot.bin"])
        self.assertEqual(self.gui._ps5_datei_modus(ftp, "/x/eboot.bin"), 0o666)

    def test_unlesbar_ergibt_null(self):
        class _Stumm:
            def sendcmd(self, _b):
                raise OSError("nix")

            def retrlines(self, _b, _c):
                raise OSError("nix")
        self.assertEqual(self.gui._ps5_datei_modus(_Stumm(), "/x"), 0)

    def test_warnung_bei_0666(self):
        ftp = _Ftp(mlst="type=file;unix.mode=0666; /x/eboot.bin")
        self.assertFalse(self.gui._warnen_wenn_nicht_ausfuehrbar(ftp, "/x/eboot.bin"))
        self.assertTrue(any("mode_not_executable" in z for z in self.protokoll))

    def test_keine_warnung_bei_0777(self):
        ftp = _Ftp(mlst="type=file;unix.mode=0777; /x/eboot.bin")
        self.assertTrue(self.gui._warnen_wenn_nicht_ausfuehrbar(ftp, "/x/eboot.bin"))
        self.assertEqual(self.protokoll, [])

    def test_keine_warnung_wenn_unbekannt(self):
        # Lieber schweigen als fälschlich warnen.
        class _Stumm:
            def sendcmd(self, _b):
                raise OSError("nix")

            def retrlines(self, _b, _c):
                raise OSError("nix")
        self.assertTrue(self.gui._warnen_wenn_nicht_ausfuehrbar(_Stumm(), "/x"))
        self.assertEqual(self.protokoll, [])

    def test_erwarteter_modus_ist_hinterlegt(self):
        self.assertEqual(PS5ConverterGUI._PS5_BENOETIGTER_MODUS, 0o777)


if __name__ == "__main__":
    unittest.main(verbosity=2)
