# -*- coding: utf-8 -*-
"""Prueft den Lesezugang zur ShadowMount+-Schnittstelle.

Angelegt am 03.09.2026.

**Gemessen, nicht gestellt.** Die Pruefungen sprechen mit einem echten
HTTP-Server auf einem echten Port - ``urllib``, Verbindungsaufbau,
Kopfzeilen, JSON, alles laeuft wirklich. Eine Attrappe von
``urllib.request.urlopen`` haette genau den Teil weggelassen, an dem
etwas schiefgehen kann.

Der Server antwortet je nach Pfad verschieden, damit auch die Faelle
geprueft werden koennen, die im Betrieb die haeufigsten sind: Der Dienst
ist gar nicht da, oder auf dem Port lauscht etwas anderes.
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import shadowmount_api as api


class _Handler(BaseHTTPRequestHandler):
    """Spielt die Schnittstelle nach - so weit, wie sie hier gebraucht wird."""

    #: Wird je Pruefung gesetzt: Pfad -> (HTTP-Code, Koerper als Bytes).
    antworten: dict = {}

    def do_POST(self) -> None:                              # noqa: N802
        laenge = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(laenge)
        code, koerper = self.antworten.get(
            self.path, (404, b'{"status":2,"error":"not found"}'))
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(koerper)))
        self.end_headers()
        self.wfile.write(koerper)

    def log_message(self, *_a) -> None:
        """Still - sonst schreibt jeder Aufruf in die Testausgabe."""


class _MitServer(unittest.TestCase):
    """Faehrt vor jeder Pruefung einen Server auf einem freien Port hoch."""

    ANTWORTEN: dict = {}

    def setUp(self) -> None:
        _Handler.antworten = dict(self.ANTWORTEN)
        # Port 0: Das Betriebssystem sucht einen freien aus. Ein fester
        # Port waere auf einem Rechner, auf dem etwas anderes lauscht,
        # ein sporadischer Fehlschlag.
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        self.faden = threading.Thread(target=self.server.serve_forever,
                                      daemon=True)
        self.faden.start()
        self.addCleanup(self._abbauen)

    def _abbauen(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.faden.join(timeout=5)

    def wohin(self) -> dict:
        return {"host": "127.0.0.1", "port": self.port, "zeitgrenze": 3.0}


def _koerper(objekt) -> bytes:
    return json.dumps(objekt).encode("utf-8")


class GutfallTests(_MitServer):
    """Die Konsole antwortet wie beschrieben."""

    ANTWORTEN = {
        "/api/v1/version": (200, _koerper({
            "status": 0, "api_version": 1, "shadowmount_version": "1.7",
            "capabilities": ["list_images", "list_games"]})),
        "/api/v1/images": (200, _koerper({
            "status": 0, "count": 2, "images": [
                {"path": "/mnt/usb0/A.ffpfsc", "mounted": True,
                 "complete": True, "source_available": True},
                {"path": "/mnt/usb0/B.ffpfsc", "mounted": False,
                 "complete": False, "source_available": True}]})),
        "/api/v1/games": (200, _koerper({
            "status": 0, "count": 1, "games": [
                {"title_id": "PPSA12345", "name": "Probe",
                 "source_type": "image"}]})),
        "/api/v1/storage": (200, _koerper({
            "status": 0, "count": 1, "storage": [
                {"mount_point": "/mnt/usb0", "total_bytes": 1000,
                 "available_bytes": 400}]})),
    }

    def test_die_fassung_kommt_an(self) -> None:
        antwort = api.fassung(**self.wohin())
        self.assertTrue(antwort.ok, antwort.grund)
        self.assertEqual(1, antwort.daten["api_version"])
        self.assertEqual("1.7", antwort.daten["shadowmount_version"])

    def test_erreichbar_liefert_die_fassung(self) -> None:
        da, text = api.erreichbar(**self.wohin())
        self.assertTrue(da)
        self.assertEqual("1.7", text)

    def test_abbilder_bringen_den_zustand_mit(self) -> None:
        """Der Punkt der ganzen Uebung.

        Ein Verzeichnisdurchlauf sieht zwei Dateien. Hier steht
        zusaetzlich, dass die eine eingehaengt und die andere
        unvollstaendig ist.
        """
        antwort = api.abbilder(**self.wohin())
        self.assertTrue(antwort.ok, antwort.grund)
        bilder = antwort.daten["images"]
        self.assertEqual(2, len(bilder))
        self.assertTrue(bilder[0]["mounted"])
        self.assertFalse(bilder[1]["complete"])

    def test_spiele_ohne_groesse_ist_die_vorgabe(self) -> None:
        """Sonst laeuft die Konsole jeden Spielordner durch."""
        antwort = api.spiele(**self.wohin())
        self.assertTrue(antwort.ok, antwort.grund)
        self.assertEqual("PPSA12345", antwort.daten["games"][0]["title_id"])

    def test_der_speicher_wird_gemeldet(self) -> None:
        antwort = api.speicher(**self.wohin())
        self.assertTrue(antwort.ok, antwort.grund)
        self.assertEqual(400, antwort.daten["storage"][0]["available_bytes"])


class SchlechtfallTests(_MitServer):
    """Was im Betrieb haeufiger vorkommt als der Gutfall."""

    ANTWORTEN = {
        # Ein errno-Fehler mit HTTP 200 - so beschreibt es die Doku.
        "/api/v1/version": (200, _koerper({"status": 22, "error": "EINVAL"})),
        # Etwas, das kein JSON ist: auf dem Port lauscht ein Webserver.
        "/api/v1/images": (200, b"<html><body>Hallo</body></html>"),
        # Gueltiges JSON, aber ohne "status" - also nicht ShadowMount+.
        "/api/v1/games": (200, _koerper({"hallo": "welt"})),
        # Ein echter HTTP-Fehlerschlag.
        "/api/v1/storage": (409, _koerper({"status": 16, "error": "EBUSY"})),
    }

    def test_ein_errno_gilt_als_misserfolg(self) -> None:
        antwort = api.fassung(**self.wohin())
        self.assertFalse(antwort.ok)
        self.assertIn("22", antwort.grund)
        self.assertIn("EINVAL", antwort.grund)

    def test_kein_json_wird_benannt(self) -> None:
        antwort = api.abbilder(**self.wohin())
        self.assertFalse(antwort.ok)
        self.assertIn("JSON", antwort.grund)

    def test_ohne_status_wird_nachgefragt_wer_dort_lauscht(self) -> None:
        """Der Fall, der sonst still falsche Daten liefern wuerde."""
        antwort = api.spiele(**self.wohin())
        self.assertFalse(antwort.ok)
        self.assertIn("ShadowMount", antwort.grund)

    def test_ein_http_fehler_traegt_seinen_grund(self) -> None:
        antwort = api.speicher(**self.wohin())
        self.assertFalse(antwort.ok)
        self.assertIn("409", antwort.grund)
        self.assertIn("EBUSY", antwort.grund)

    def test_nichts_davon_wirft(self) -> None:
        """Der Kern des Entwurfs.

        Eine nicht erreichbare Konsole ist der Normalfall - der Dienst
        lauscht ab Werk nur auf der Rueckschleife der PS5. Wer jeden
        Aufruf einpacken muesste, packt irgendwann einen nicht ein.
        """
        for aufruf in (api.fassung, api.abbilder, api.spiele, api.speicher):
            with self.subTest(aufruf=aufruf.__name__):
                self.assertIsInstance(aufruf(**self.wohin()), api.Antwort)


class NichtErreichbarTests(unittest.TestCase):
    """Ohne Server - der haeufigste Fall ueberhaupt."""

    def _wohin(self) -> dict:
        import socket

        # Einen Port belegen und sofort wieder freigeben: Danach ist er
        # mit hoher Wahrscheinlichkeit frei, und niemand antwortet dort.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        return {"host": "127.0.0.1", "port": port, "zeitgrenze": 2.0}

    def test_der_grund_steht_im_klartext(self) -> None:
        antwort = api.fassung(**self._wohin())
        self.assertFalse(antwort.ok)
        self.assertIn("nicht erreichbar", antwort.grund)

    def test_erreichbar_meldet_falsch_ohne_zu_werfen(self) -> None:
        da, grund = api.erreichbar(**self._wohin())
        self.assertFalse(da)
        self.assertTrue(grund.strip(), "Ohne Grund kann der Anwender nichts tun.")


class EntwurfTests(unittest.TestCase):
    """Was das Modul bewusst NICHT kann."""

    SCHREIBENDE = ("mount", "unmount", "uninstall", "delete", "move",
                   "copy", "unpack", "settings/update", "manual/add",
                   "manual/remove", "scan")

    def test_kein_schreibender_endpunkt_ist_eingebaut(self) -> None:
        """Ein Konvertierprogramm loescht nichts auf der Konsole.

        Gesucht wird im Quelltext, und das ist hier ausnahmsweise
        richtig: Die Aussage lautet "diese Pfade kommen nicht vor",
        nicht "dieser Weg verhaelt sich so".
        """
        quelle = Path(api.__file__).read_text(encoding="utf-8")
        # Der Modulkopf nennt die verbotenen Namen, um zu erklaeren,
        # warum sie fehlen - deshalb nur der Code darunter.
        code = quelle.split('"""', 2)[-1]
        for name in self.SCHREIBENDE:
            with self.subTest(endpunkt=name):
                self.assertNotIn('"/api/v1/games/%s"' % name, code)
                self.assertNotIn('"/api/v1/%s"' % name, code)

    def test_die_vier_lesenden_sind_da(self) -> None:
        """Gegenprobe: sonst hiesse "nichts Schreibendes" auch "nichts"."""
        for name in ("fassung", "abbilder", "spiele", "speicher", "erreichbar"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(api, name, None)))

    def test_die_vorgaben_stimmen_mit_der_konsole_ueberein(self) -> None:
        """``config.ini.example`` von 1.7alpha13 nennt 127.0.0.1:10101."""
        self.assertEqual("127.0.0.1", api.STANDARD_HOST)
        self.assertEqual(10101, api.STANDARD_PORT)

    def test_eine_zu_grosse_anfrage_wird_hier_abgefangen(self) -> None:
        """Die Konsole nimmt hoechstens 4096 Bytes - das sagt sie sonst
        erst mit HTTP 413."""
        antwort = api._fragen("/api/v1/games", {"x": "y" * 5000},
                              host="127.0.0.1", port=1)
        self.assertFalse(antwort.ok)
        self.assertIn("zu gross", antwort.grund)


if __name__ == "__main__":
    unittest.main(verbosity=2)
