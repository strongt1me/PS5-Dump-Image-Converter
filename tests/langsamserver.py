# -*- coding: utf-8 -*-
"""Lokaler Langsam-Server fuer die Tests von ABBRECHEN und Fortschritt (``test_netz_abbruch``, ``test_download_fenster``).

Drei Verhalten, gewaehlt nach Pfad: ``/trickle/..`` (16 KiB je 0,2 s), ``/spaet/..`` (Kopfzeilen erst nach 8 s),
``/stumm/..`` (4 KiB, dann Funkstille), sonst schnell. Unterstuetzt ``Range``-Anfragen nicht - die Tests laden von vorn.
"""
from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading

GROESSE = 4 * 1024 * 1024
DATEN = (b"0123456789abcdef" * 1024) * (GROESSE // 16384)
SHA = hashlib.sha256(DATEN).hexdigest()
#: Eine Reaktion auf ABBRECHEN darf hoechstens so lange dauern (vorher 10 bis 21 s).
GRENZE = 2.5


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a) -> None:
        pass

    def do_GET(self) -> None:
        szenario = self.path.strip("/").split("/")[0]
        stop: threading.Event = self.server.stop
        try:
            if szenario == "spaet" and stop.wait(8):          # Kopfzeilen erst nach 8 s
                return
            self.send_response(200)
            self.send_header("Content-Length", str(GROESSE))
            self.end_headers()
            pos = 0
            while pos < GROESSE and not stop.is_set():
                if szenario == "trickle":                     # 16 KiB je 0,2 s, rund 80 KB/s
                    self.wfile.write(DATEN[pos:pos + 16384])
                    self.wfile.flush()
                    pos += 16384
                    stop.wait(0.2)
                elif szenario == "stumm":                     # 4 KiB, dann Funkstille
                    self.wfile.write(DATEN[pos:pos + 4096])
                    self.wfile.flush()
                    pos += 4096
                    stop.wait(3600)
                else:
                    self.wfile.write(DATEN[pos:pos + 262144])
                    pos += 262144
        except OSError:
            return


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.stop = threading.Event()
