# -*- coding: utf-8 -*-
"""Ein Spiel auf der PS5 starten - ueber websrv (27.09.2026).

Geprueft gegen einen kleinen HTTP-Server auf dem eigenen Rechner, der so
antwortet wie websrv (``src/websrv.c``, ``launch_request``, Tags v0.20 bis
v0.34): 200 gestartet, 503 abgelehnt, 400 ohne Kennung - und 404 fuer einen
Pfad, den der Server nicht kennt. An der echten Konsole ist der Start nicht
gelaufen; das ist ein Starttest und bleibt dem Nutzer.
"""
from __future__ import annotations

import http.server
import socket
import sys
import threading
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import titelstart                  # noqa: E402


def _freier_port() -> int:
    """Ein Port, auf dem gerade sicher niemand lauscht."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class TitelstartTests(unittest.TestCase):

    def setUp(self) -> None:
        class Websrv(http.server.BaseHTTPRequestHandler):
            antwort = 200
            anfragen: list = []

            def do_GET(self) -> None:          # noqa: N802 - Name von http.server
                type(self).anfragen.append(self.path)
                self.send_response(type(self).antwort)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_a) -> None:
                pass

        self.websrv = Websrv
        self.server = http.server.HTTPServer(("127.0.0.1", 0), Websrv)
        self.port = self.server.server_address[1]
        faden = threading.Thread(target=self.server.serve_forever, daemon=True)
        faden.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _starten(self, antwort: int, kennung: str = "PPSA01325") -> tuple[str, str]:
        self.websrv.antwort = antwort
        return titelstart.titel_starten("127.0.0.1", kennung, port=self.port, zeit=5)

    def test_gestartet_und_die_anfrage_wie_websrv_sie_erwartet(self) -> None:
        self.assertEqual(titelstart.GESTARTET, self._starten(200)[0])
        self.assertEqual(["/launch?titleId=PPSA01325"], self.websrv.anfragen)

    def test_die_konsole_lehnt_ab(self) -> None:
        self.assertEqual(titelstart.ABGELEHNT, self._starten(503)[0])

    def test_ein_webserver_ohne_launch(self) -> None:
        self.assertEqual(titelstart.UNBEKANNTER_PFAD, self._starten(404)[0])

    def test_andere_antworten_sind_fehler(self) -> None:
        for antwort in (400, 500):
            with self.subTest(antwort=antwort):
                ergebnis, einzelheit = self._starten(antwort)
                self.assertEqual(titelstart.FEHLER, ergebnis)
                self.assertIn(str(antwort), einzelheit)

    def test_kleinschreibung_wird_zur_kennung(self) -> None:
        self.assertEqual(titelstart.GESTARTET, self._starten(200, "cusa24767")[0])
        self.assertEqual(["/launch?titleId=CUSA24767"], self.websrv.anfragen)

    def test_ohne_gueltige_kennung_geht_keine_anfrage_hinaus(self) -> None:
        for falsch in ("", "PPSA0132", "../etc", "PPSA01325&x=1"):
            with self.subTest(kennung=falsch):
                self.assertEqual(titelstart.FEHLER, self._starten(200, falsch)[0])
        self.assertEqual([], self.websrv.anfragen)

    def test_nichts_lauscht(self) -> None:
        ergebnis, _einzelheit = titelstart.titel_starten(
            "127.0.0.1", "PPSA01325", port=_freier_port(), zeit=3)
        self.assertEqual(titelstart.NICHT_ERREICHBAR, ergebnis)


if __name__ == "__main__":
    unittest.main(verbosity=2)
