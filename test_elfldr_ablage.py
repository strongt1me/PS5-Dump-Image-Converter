# -*- coding: utf-8 -*-
"""elfldr per FTP in den Ordner des Payload Managers - nur, wenn es fehlt.

Wunsch des Nutzers vom 26.09.2026: "Wenn der Port 9021 nicht offen ist, soll
dieser Ordner (falls noch nicht vorhanden auf der PS5) per FTP an die PS5
hochgeladen werden (/data/pldmgr/payloads) und die .elf per Payload Manager
automatisch geladen werden." Der Ordner auf seiner Konsole heisst ``elfldr``
und traegt ``elfldr-ps5_v0.26.elf`` samt der Begleitdatei ``.elf.json``, die
der Payload Manager selbst angelegt hat.

Die Gegenstelle ist ein FTP-Server im Speicher, der jeden Befehl mitschreibt:
So laesst sich pruefen, dass nichts unter dem endgueltigen Namen halb
ankommt, dass eine fremde Datei unangetastet bleibt und dass nichts
geloescht wird.
"""
from __future__ import annotations

import ftplib
import json
import posixpath
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import konsole_ftp                  # noqa: E402
from ps5_validator.utils import payload_versand as pv       # noqa: E402

ORDNER = "/data/pldmgr/payloads/elfldr"
ZIEL = ORDNER + "/" + pv.ELFLDR_NAME
ELF = b"\x7fELF" + bytes(range(256)) * 4


class _FtpImSpeicher:
    """Ein FTP-Server im Speicher - nur, was konsole_ftp davon braucht."""

    def __init__(self, dateien=None, mit_groesse: bool = True,
                 begleitdatei_scheitert: bool = False) -> None:
        self.dateien = dict(dateien or {})
        self.ordner = {"/", "/data", "/data/pldmgr", "/data/pldmgr/payloads"}
        for pfad in self.dateien:
            teil = posixpath.dirname(pfad)
            while teil not in ("", "/"):
                self.ordner.add(teil)
                teil = posixpath.dirname(teil)
        self.mit_groesse = mit_groesse
        self.begleitdatei_scheitert = begleitdatei_scheitert
        self.hier = "/"
        self.befehle: list = []

    def arten(self, *gesucht: str) -> list:
        return [b for b in self.befehle if b[0] in gesucht]

    def cwd(self, pfad: str) -> None:
        if pfad not in self.ordner:
            raise ftplib.error_perm("550 %s: kein Ordner" % pfad)
        self.hier = pfad

    def mlsd(self, *_a, **_k):
        for ordner in sorted(self.ordner):
            if ordner != self.hier and posixpath.dirname(ordner) == self.hier:
                yield posixpath.basename(ordner), {"type": "dir"}
        for pfad, inhalt in sorted(self.dateien.items()):
            if posixpath.dirname(pfad) == self.hier:
                fakten = {"type": "file"}
                if self.mit_groesse:
                    fakten["size"] = str(len(inhalt))
                yield posixpath.basename(pfad), fakten

    def mkd(self, pfad: str) -> str:
        self.befehle.append(("MKD", pfad))
        if pfad in self.ordner or posixpath.dirname(pfad) not in self.ordner:
            raise ftplib.error_perm("550 %s" % pfad)
        self.ordner.add(pfad)
        return pfad

    def storbinary(self, befehl: str, strom, blocksize: int = 8192,
                   callback=None, rest=None) -> str:
        pfad = befehl.split(" ", 1)[1]
        self.befehle.append(("STOR", pfad))
        if self.begleitdatei_scheitert and pfad.endswith(".json" + konsole_ftp.ZWISCHEN_ENDUNG):
            raise ftplib.error_perm("553 nicht erlaubt")
        if posixpath.dirname(pfad) not in self.ordner:
            raise ftplib.error_perm("553 %s: kein Ordner" % pfad)
        self.dateien[pfad] = strom.read()
        return "226 ok"

    def rename(self, alt: str, neu: str) -> str:
        self.befehle.append(("RENAME", alt, neu))
        if alt not in self.dateien:
            raise ftplib.error_perm("550 %s" % alt)
        self.dateien[neu] = self.dateien.pop(alt)
        return "250 ok"

    def size(self, pfad: str) -> int:
        self.befehle.append(("SIZE", pfad))
        if pfad not in self.dateien:
            raise ftplib.error_perm("550 %s" % pfad)
        return len(self.dateien[pfad])

    def delete(self, pfad: str) -> str:
        self.befehle.append(("DELE", pfad))
        self.dateien.pop(pfad, None)
        return "250 ok"

    def quit(self) -> str:
        self.befehle.append(("QUIT",))
        return "221 bye"

    def close(self) -> None:
        pass


class _MitFtp(unittest.TestCase):

    def _ftp(self, server: _FtpImSpeicher) -> _FtpImSpeicher:
        flicken = mock.patch.object(konsole_ftp, "verbinden",
                                    lambda adresse, port=konsole_ftp.FTP_PORT, zeit=10.0: server)
        flicken.start()
        self.addCleanup(flicken.stop)
        return server


class BegleitdateiTests(unittest.TestCase):
    """Die .json neben der .elf - so, wie der Payload Manager sie selbst anlegt."""

    def test_wie_das_original_auf_der_konsole(self) -> None:
        """Zeichen fuer Zeichen die Datei vom 25.09.2026 21:05:40 (355 Bytes)."""
        erwartet = (
            '{\n  "name": "elfldr-ps5_v0.26.elf",\n'
            '  "filename": "elfldr-ps5_v0.26.elf",\n  "url": "",\n'
            '  "source": "",\n  "source_direct": "",\n  "description": "",\n'
            '  "last_update": "",\n  "version": "",\n  "checksum": "",\n'
            '  "category": "",\n  "downloaded_at": "2026-09-25T21:05:40+0200",\n'
            '  "install_source": "web_upload",\n  "install_source_detail": "",\n'
            '  "source_name": ""\n}\n').encode("utf-8")
        zeit = datetime(2026, 9, 25, 21, 5, 40, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(355, len(erwartet))
        self.assertEqual(erwartet, pv.elfldr_begleitdatei("elfldr-ps5_v0.26.elf", zeit))

    def test_ohne_zeitpunkt_die_ortszeit_von_jetzt(self) -> None:
        angaben = json.loads(pv.elfldr_begleitdatei("a.elf"))
        self.assertRegex(angaben["downloaded_at"],
                         r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}$")
        self.assertEqual(("a.elf", "a.elf"), (angaben["name"], angaben["filename"]))


class AblegenTests(_MitFtp):
    """elfldr_ablegen: hochladen nur, was fehlt - nie halb, nie ueber Fremdes."""

    def test_fehlt_der_ordner_kommt_er_per_ftp(self) -> None:
        server = self._ftp(_FtpImSpeicher())
        ablage = pv.elfldr_ablegen("10.0.0.5", ELF)
        self.assertEqual(pv.ElfldrAblage(ZIEL, pv.ABLAGE_FTP), ablage)
        self.assertEqual(ELF, server.dateien[ZIEL])
        self.assertEqual(pv.ELFLDR_NAME, json.loads(server.dateien[ZIEL + ".json"])["name"])
        self.assertIn(("MKD", ORDNER), server.befehle)
        self.assertEqual([ZIEL + ".tmp", ZIEL + ".json.tmp"],
                         [b[1] for b in server.arten("STOR")],
                         "Unter dem endgueltigen Namen darf nie etwas halb ankommen.")
        self.assertEqual([], server.arten("DELE"))
        self.assertEqual([("QUIT",)], server.arten("QUIT"))

    def test_liegt_er_schon_da_wird_nichts_hochgeladen(self) -> None:
        begleitdatei = b'{"name": "vom Payload Manager"}\n'
        server = self._ftp(_FtpImSpeicher({ZIEL: ELF, ZIEL + ".json": begleitdatei}))
        ablage = pv.elfldr_ablegen("10.0.0.5", ELF)
        self.assertEqual(pv.ElfldrAblage(ZIEL, pv.ABLAGE_VORHANDEN), ablage)
        self.assertEqual([], server.arten("STOR", "MKD", "RENAME", "DELE"))
        self.assertEqual(begleitdatei, server.dateien[ZIEL + ".json"])

    def test_fehlt_nur_die_begleitdatei_kommt_sie_nach(self) -> None:
        server = self._ftp(_FtpImSpeicher({ZIEL: ELF}))
        ablage = pv.elfldr_ablegen("10.0.0.5", ELF)
        self.assertEqual(pv.ABLAGE_VORHANDEN, ablage.art)
        self.assertEqual([ZIEL + ".json.tmp"], [b[1] for b in server.arten("STOR")])
        self.assertIn(ZIEL + ".json", server.dateien)

    def test_eine_andere_datei_bleibt_unangetastet(self) -> None:
        server = self._ftp(_FtpImSpeicher({ZIEL: b"etwas anderes"}))
        with self.assertRaises(pv.AblageBelegt) as fall:
            pv.elfldr_ablegen("10.0.0.5", ELF)
        meldung = str(fall.exception)
        for teil in (ZIEL, "13", str(len(ELF))):
            self.assertIn(teil, meldung)
        self.assertEqual([], server.arten("STOR", "RENAME", "DELE"))
        self.assertEqual(b"etwas anderes", server.dateien[ZIEL])
        self.assertEqual([("QUIT",)], server.arten("QUIT"))

    def test_ohne_groessenangabe_fragt_size_nach(self) -> None:
        """Eine Auflistung ohne Groesse liefert 0 - das ist kein fremdes elfldr."""
        server = self._ftp(_FtpImSpeicher({ZIEL: ELF, ZIEL + ".json": b"{}"},
                                          mit_groesse=False))
        self.assertEqual(pv.ABLAGE_VORHANDEN, pv.elfldr_ablegen("10.0.0.5", ELF).art)
        self.assertEqual([("SIZE", ZIEL)], server.arten("SIZE"))
        self.assertEqual([], server.arten("STOR"))

    def test_scheitert_die_begleitdatei_bleibt_es_beim_elf(self) -> None:
        server = self._ftp(_FtpImSpeicher(begleitdatei_scheitert=True))
        with self.assertLogs(pv.logger, "WARNING"):
            ablage = pv.elfldr_ablegen("10.0.0.5", ELF)
        self.assertEqual(pv.ABLAGE_FTP, ablage.art)
        self.assertEqual(ELF, server.dateien[ZIEL])
        self.assertNotIn(ZIEL + ".json", server.dateien)

    def test_die_meldung_kommt_uebersetzt(self) -> None:
        self._ftp(_FtpImSpeicher({ZIEL: b"x"}))
        with self.assertRaises(pv.AblageBelegt) as fall:
            pv.elfldr_ablegen("10.0.0.5", ELF,
                              texte={"elfldr_belegt": "EN {pfad} {ist} {soll}"})
        self.assertEqual("EN %s 1 %d" % (ZIEL, len(ELF)), str(fall.exception))


class LadenTests(_MitFtp):
    """elfldr_laden: aus dem Ordner des Payload Managers, sonst ueber seine Weboberflaeche."""

    def setUp(self) -> None:
        self.rufe: list = []

        def _ruf(host, pfad, koerper=None, port=pv.PLDMGR_PORT, timeout=0):
            self.rufe.append(pfad)
            return '{"folder_name": "elfldr"}'

        flicken = mock.patch.object(pv, "_pldmgr_ruf", _ruf)
        flicken.start()
        self.addCleanup(flicken.stop)

    def test_per_ftp_abgelegt_dann_nur_geladen(self) -> None:
        self._ftp(_FtpImSpeicher())
        ablage = pv.elfldr_laden("10.0.0.5", ELF)
        self.assertEqual(pv.ABLAGE_FTP, ablage.art)
        self.assertEqual(["/loadpayload:" + ZIEL], self.rufe,
                         "Liegt elfldr per FTP da, braucht es die Weboberflaeche nicht.")

    def test_liegt_es_schon_da_wird_nur_geladen(self) -> None:
        server = self._ftp(_FtpImSpeicher({ZIEL: ELF, ZIEL + ".json": b"{}"}))
        self.assertEqual(pv.ABLAGE_VORHANDEN, pv.elfldr_laden("10.0.0.5", ELF).art)
        self.assertEqual(["/loadpayload:" + ZIEL], self.rufe)
        self.assertEqual([], server.arten("STOR"))

    def test_ohne_ftp_ueber_die_weboberflaeche(self) -> None:
        def _kein_ftp(adresse, port=konsole_ftp.FTP_PORT, zeit=10.0):
            raise konsole_ftp.FtpFehler("10.0.0.5:2121 nicht erreichbar")

        with mock.patch.object(konsole_ftp, "verbinden", _kein_ftp):
            ablage = pv.elfldr_laden("10.0.0.5", ELF)
        self.assertEqual(pv.ABLAGE_WEB, ablage.art)
        self.assertIn("2121", ablage.grund)
        self.assertEqual(["/manage:check", "/manage:upload", "/loadpayload:" + ZIEL],
                         [r.split("?")[0] for r in self.rufe])

    def test_eine_fremde_datei_laedt_nichts(self) -> None:
        self._ftp(_FtpImSpeicher({ZIEL: b"etwas anderes"}))
        with self.assertRaises(pv.AblageBelegt):
            pv.elfldr_laden("10.0.0.5", ELF)
        self.assertEqual([], self.rufe,
                         "Weder die fremde Datei laden noch sie ueber die Weboberflaeche ersetzen.")


class AufweckenTests(unittest.TestCase):
    """elfldr_aufwecken: laden, dann den Port alle 0,5 s fragen."""

    def _lauf(self, offen_ab: int, warten: float = 45.0):
        uhr = [0.0]
        schlaefe: list = []
        fragen = [0]
        geladen: list = []

        def _schlafen(sekunden):
            schlaefe.append(sekunden)
            uhr[0] += sekunden

        def _offen(host, port, timeout=1.5):
            fragen[0] += 1
            return fragen[0] > offen_ab

        falsche_zeit = types.SimpleNamespace(monotonic=lambda: uhr[0], sleep=_schlafen)
        with mock.patch.object(pv, "time", falsche_zeit), \
                mock.patch.object(pv, "port_offen", _offen), \
                mock.patch.object(pv, "elfldr_laden",
                                  lambda *a, **k: geladen.append((a, k))):
            ergebnis = pv.elfldr_aufwecken("10.0.0.5", ELF, warten=warten,
                                           texte={"x": "y"})
        return ergebnis, schlaefe, geladen

    def test_der_port_geht_auf(self) -> None:
        ergebnis, schlaefe, geladen = self._lauf(offen_ab=2)
        self.assertTrue(ergebnis)
        self.assertEqual([0.5, 0.5], schlaefe)
        self.assertEqual(1, len(geladen))
        self.assertEqual({"x": "y"}, geladen[0][1].get("texte"))

    def test_der_port_bleibt_zu(self) -> None:
        ergebnis, schlaefe, _geladen = self._lauf(offen_ab=10 ** 6, warten=3.0)
        self.assertFalse(ergebnis)
        self.assertEqual({0.5}, set(schlaefe))
        self.assertAlmostEqual(3.0, sum(schlaefe), delta=0.51)


class SendenTests(unittest.TestCase):
    """senden: ist das Payload elfldr selbst, geht es nach dem Wecken nicht noch einmal hinaus."""

    def setUp(self) -> None:
        ordner = tempfile.TemporaryDirectory()
        self.addCleanup(ordner.cleanup)
        self.elfldr = Path(ordner.name) / pv.ELFLDR_NAME
        self.elfldr.write_bytes(ELF)
        # Haelt einen verbotenen Umweg an - ob er kam, prueft die Aufraeumrunde.
        umweg = mock.Mock(side_effect=AssertionError("direkter Umweg"))
        self.addCleanup(umweg.assert_not_called)
        for name, ersatz in (
                ("port_offen", lambda host, port, timeout=1.5: int(port) == pv.PLDMGR_PORT),
                ("ueber_pldmgr", umweg)):
            flicken = mock.patch.object(pv, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)

    def test_elfldr_selbst_geht_kein_zweites_mal_hinaus(self) -> None:
        with mock.patch.object(pv, "elfldr_aufwecken", return_value=True), \
                mock.patch.object(pv, "ueber_elfldr",
                                  side_effect=AssertionError("zweites Mal geschickt")) as zweit:
            ergebnis = pv.senden("10.0.0.5", ELF, pv.ELFLDR_NAME,
                                 elfldr_pfad=str(self.elfldr))
        self.assertEqual((pv.WEG_GEWECKT, "", pv.ELFLDR_NAME), ergebnis)
        zweit.assert_not_called()

    def test_ein_anderes_payload_folgt_ueber_9021(self) -> None:
        with mock.patch.object(pv, "elfldr_aufwecken", return_value=True), \
                mock.patch.object(pv, "ueber_elfldr", return_value="ok") as danach:
            ergebnis = pv.senden("10.0.0.5", b"\x7fELF anderes", "klogsrv.elf",
                                 elfldr_pfad=str(self.elfldr))
        self.assertEqual((pv.WEG_GEWECKT, "ok", pv.ELFLDR_NAME), ergebnis)
        danach.assert_called_once()

    def test_die_texte_gehen_an_das_wecken(self) -> None:
        with mock.patch.object(pv, "elfldr_aufwecken", return_value=True) as wecken, \
                mock.patch.object(pv, "ueber_elfldr", return_value=""):
            pv.senden("10.0.0.5", ELF, pv.ELFLDR_NAME, elfldr_pfad=str(self.elfldr),
                      texte={"elfldr_belegt": "x"})
        self.assertEqual({"elfldr_belegt": "x"}, wecken.call_args.kwargs.get("texte"))


if __name__ == "__main__":
    unittest.main()
