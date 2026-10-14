# -*- coding: utf-8 -*-
"""Payload Manager 0.6.0 (itsPLK, 14.10.2026): Aktionen nur per POST, ohne Browser-Origin nur mit ``X-PLDMGR-Request: 1``.

Bis dahin schickte das Programm ``/loadpayload:`` per GET und ohne den Kopf - der zweite Sendeweg (Port 9021 zu) waere mit
0.6.0 an 405/403 gescheitert. Geprueft gegen einen Nachbau der Regeln aus ``src/http_server.c`` (``is_mutation_route``,
``mutation_authorized``) und gegen das nachsichtige Verhalten von 0.5.2.
"""
from __future__ import annotations

import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import payload_versand as pv     # noqa: E402

AKTIONEN = ("/manage:upload", "/loadpayload:")


def _server(streng: bool):
    aufrufe: list = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _antwort(self, code: int, text: str = "") -> None:
            daten = text.encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(daten)))
            self.end_headers()
            self.wfile.write(daten)

        def _behandeln(self, methode: str) -> None:
            laenge = int(self.headers.get("Content-Length") or 0)
            koerper = self.rfile.read(laenge) if laenge else b""
            aufrufe.append((methode, self.path, self.headers.get("X-PLDMGR-Request"), len(koerper)))
            aktion = self.path.startswith(AKTIONEN)
            if streng:
                if methode != ("POST" if aktion else "GET"):
                    return self._antwort(405)
                if aktion and self.headers.get("X-PLDMGR-Request") != "1" and not self.headers.get("Origin"):
                    return self._antwort(403, "Mutation origin or request marker rejected")
            if self.path.startswith("/manage:check"):
                return self._antwort(200, '{"folder_name": "probe"}')
            return self._antwort(200, "OK")

        def do_GET(self):  # noqa: N802
            self._behandeln("GET")

        def do_POST(self):  # noqa: N802
            self._behandeln("POST")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, aufrufe


class PayloadManager060Tests(unittest.TestCase):

    def _senden(self, streng: bool) -> list:
        server, aufrufe = _server(streng)
        self.addCleanup(server.shutdown)
        ziel = pv.ueber_pldmgr("127.0.0.1", b"\x7fELF" + b"x" * 100, "probe.elf", port=server.server_address[1])
        self.assertEqual("%s/probe/probe.elf" % pv.PLDMGR_ABLAGE, ziel)
        return aufrufe

    def test_mit_0_6_0_kommt_das_payload_an(self) -> None:
        aufrufe = self._senden(streng=True)
        self.assertTrue(aufrufe[0][1].startswith("/manage:check"))
        self.assertEqual("GET", aufrufe[0][0], "die Abfrage bleibt ein GET")
        self.assertEqual(("POST", "1"), (aufrufe[1][0], aufrufe[1][2]), "Upload per POST mit Kennzeichen")
        self.assertTrue(aufrufe[2][1].startswith("/loadpayload:"))
        self.assertEqual(("POST", "1"), (aufrufe[2][0], aufrufe[2][2]), "Start per POST mit Kennzeichen")
        self.assertEqual(104, aufrufe[1][3], "der Upload traegt das ELF")

    def test_mit_0_5_2_geht_es_weiter(self) -> None:
        self.assertEqual(3, len(self._senden(streng=False)))


if __name__ == "__main__":
    unittest.main()
