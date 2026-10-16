# -*- coding: utf-8 -*-
"""Kaputte HTTP-Antworten an allen Stellen, die ``urllib`` benutzen.

``urllib`` meldet eine Antwort mit unlesbarer Statuszeile (``BadStatusLine``) oder eine abgerissene
``Transfer-Encoding: chunked``-Antwort (``IncompleteRead``) als ``http.client.HTTPException`` - und die ist weder ein
``OSError`` noch ein ``URLError``. Wer nur diese beiden faengt, gibt der Oberflaeche eine rohe Ausnahme statt der
Meldung "nicht erreichbar" (eingebettete Server der Konsole schicken so etwas, wenn sie mitten in der Antwort
abbrechen). Gemessen am 16.10.2026 mit einem lokalen Server, der diese Antworten schickt.

Dazu: Ein volles Laufwerk beim Schreiben der PS4-Updatedatei hiess "Netzwerkfehler" statt "schreiben".
"""
from __future__ import annotations

import ast
import errno
import hashlib
import http.client
import http.server
import io
import socketserver
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import (  # noqa: E402
    payload_versand, ps4pkg_updates, shadowmount_api, werkzeugstaende)


def _server(antwort) -> tuple:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def do_GET(self):  # noqa: N802
            antwort(self)

        do_POST = do_GET  # noqa: N815

    class Ruhig(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    httpd = Ruhig(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _statuszeile_kaputt(h) -> None:
    h.wfile.write(b"KEIN HTTP\r\n\r\n")


def _chunked_abgerissen(h) -> None:
    h.send_response(200)
    h.send_header("Transfer-Encoding", "chunked")
    h.end_headers()
    h.wfile.write(b"3e8\r\n" + b"x" * 1000 + b"\r\n")      # ein Stueck, dann reisst es ab


class _Basis(unittest.TestCase):

    def _starten(self, antwort) -> int:
        httpd, port = _server(antwort)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return port


class PayloadManagerTests(_Basis):

    def test_kaputte_statuszeile_ist_ein_oserror(self):
        port = self._starten(_statuszeile_kaputt)
        with self.assertRaises(OSError):
            payload_versand._pldmgr_ruf("127.0.0.1", "/manage:check?filename=a", port=port, timeout=5)

    def test_abgerissene_chunked_antwort_ist_ein_oserror(self):
        port = self._starten(_chunked_abgerissen)
        with self.assertRaises(OSError):
            payload_versand._pldmgr_ruf("127.0.0.1", "/manage:check?filename=a", port=port, timeout=5)


class Ps4UpdateTests(_Basis):

    def test_abfrage_mit_kaputter_statuszeile(self):
        port = self._starten(_statuszeile_kaputt)
        with self.assertRaises(ps4pkg_updates.UpdateFehler) as ctx:
            ps4pkg_updates.standard_holen("http://127.0.0.1:%d/x" % port, zeit=5)
        self.assertEqual("netz", ctx.exception.schluessel)

    def test_abfrage_mit_abgerissener_chunked_antwort(self):
        port = self._starten(_chunked_abgerissen)
        with self.assertRaises(ps4pkg_updates.UpdateFehler) as ctx:
            ps4pkg_updates.standard_holen("http://127.0.0.1:%d/x" % port, zeit=5)
        self.assertEqual("netz", ctx.exception.schluessel)

    @staticmethod
    def _info(daten: bytes) -> ps4pkg_updates.UpdateInfo:
        teil = ps4pkg_updates.UpdateTeil("http://127.0.0.1/t", 0, len(daten), hashlib.sha256(daten).hexdigest())
        return ps4pkg_updates.UpdateInfo(
            title_id="CUSA00001",
            verzeichnis=ps4pkg_updates.UpdateVerzeichnis(gesamtgroesse=len(daten), anzahl=1, teile=[teil]))

    def test_download_mit_abgerissener_antwort_ist_ein_netzfehler(self):
        class Abriss:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self, _n):
                raise http.client.IncompleteRead(b"x" * 10, 90)

        import tempfile
        with tempfile.TemporaryDirectory(prefix="ps4upd_") as ordner:
            with self.assertRaises(ps4pkg_updates.UpdateFehler) as ctx:
                ps4pkg_updates.herunterladen(self._info(b"x" * 100), ordner, oeffnen=lambda _u: Abriss())
        self.assertEqual("netz", ctx.exception.schluessel)

    def test_volles_laufwerk_heisst_schreiben_nicht_netz(self):
        daten = b"y" * 100_000
        echt = open

        class Voll:
            def __init__(self, datei):
                self.datei = datei

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                self.datei.close()
                return False

            def seek(self, *a):
                return self.datei.seek(*a)

            def write(self, _b):
                raise OSError(errno.ENOSPC, "No space left on device")

            def flush(self):
                self.datei.flush()

        def falsches_open(pfad, modus="r", *a, **k):
            if modus in ("wb", "r+b"):
                return Voll(echt(pfad, modus, *a, **k))
            return echt(pfad, modus, *a, **k)

        import tempfile
        with tempfile.TemporaryDirectory(prefix="ps4upd_") as ordner, \
                mock.patch.object(ps4pkg_updates, "open", falsches_open, create=True):
            with self.assertRaises(ps4pkg_updates.UpdateFehler) as ctx:
                ps4pkg_updates.herunterladen(self._info(daten), ordner, oeffnen=lambda _u: io.BytesIO(daten))
        self.assertEqual("schreiben", ctx.exception.schluessel)


class ShadowMountApiTests(_Basis):

    def test_kaputte_statuszeile_wirft_nicht(self):
        port = self._starten(_statuszeile_kaputt)
        antwort = shadowmount_api._fragen("/api/v1/version", host="127.0.0.1", port=port, zeitgrenze=5)
        self.assertFalse(antwort.ok)
        self.assertTrue(antwort.grund)

    def test_abgerissene_chunked_antwort_wirft_nicht(self):
        port = self._starten(_chunked_abgerissen)
        antwort = shadowmount_api._fragen("/api/v1/version", host="127.0.0.1", port=port, zeitgrenze=5)
        self.assertFalse(antwort.ok)
        self.assertTrue(antwort.grund)


class SpiegelTests(_Basis):

    def test_kaputte_statuszeile_ist_ein_oserror(self):
        port = self._starten(_statuszeile_kaputt)
        with self.assertRaises(OSError):
            werkzeugstaende.spiegel_holen("http://127.0.0.1:%d/x" % port, zeitgrenze=5)

    def test_abgerissene_chunked_antwort_ist_ein_oserror(self):
        port = self._starten(_chunked_abgerissen)
        with self.assertRaises(OSError):
            werkzeugstaende.spiegel_holen("http://127.0.0.1:%d/x" % port, zeitgrenze=5)



# ---------------------------------------------------------------------------
# Waechter: jeder Netzaufruf faengt HTTPException - oder sein Aufrufer faengt Exception
# ---------------------------------------------------------------------------
#: Netzaufrufe, die selbst keine ``HTTPException`` fangen, weil jeder Aufrufer ``except Exception`` hat
#: (Datei, innerste Funktion). Neue Eintraege nur mit Begruendung.
AUFRUFER_FAENGT_ALLES = {
    # Aufrufer: _ampr_nach_updates_sehen (try/except Exception), ampr_updates.holen (except Exception)
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_ampr_lade_adresse"),
    # Aufrufer: aktualisierungen.pruefe im Faden des Fensters (try/except Exception)
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_aktualisierungen_holen"),
    # Aufrufer: die Installationswege (try/except Exception, Rueckgabe False)
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_installer_laden"),
    # Der Netzaufruf steckt im Rueckruf ``opener``; ``herunterladen`` fasst ihn in ein try mit HTTPException.
    ("ps5_validator/utils/ps4pkg_updates.py", "herunterladen"),
    # Innerer Lader; ``_teil_laden`` darueber faengt HTTPException und wiederholt.
    ("ps5_validator/utils/ps5_updates.py", "_teil_einmal"),
    # Netz-Klasse; ihre Aufrufer (``pruefen``, ``holen``) fangen Exception je Quelle bzw. Werkzeug.
    ("ps5_validator/utils/werkzeug_updates.py", "abfragen"),
    ("ps5_validator/utils/werkzeug_updates.py", "laden"),
    ("ps5_validator/utils/werkzeug_updates.py", "bytes"),
}
_ALLES = {"Exception", "BaseException", "HTTPException", "<bare>"}


def _handlernamen(h: ast.ExceptHandler) -> set:
    if h.type is None:
        return {"<bare>"}
    knoten = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return {k.attr if isinstance(k, ast.Attribute) else getattr(k, "id", "") for k in knoten}


def _ist_netzaufruf(c: ast.Call) -> bool:
    f = c.func
    if isinstance(f, ast.Attribute) and f.attr == "urlopen":
        return True
    if isinstance(f, ast.Name) and f.id == "urlopen":
        return True
    if isinstance(f, ast.Attribute) and f.attr == "open" and isinstance(f.value, ast.Call):
        g = f.value.func                       # ``_oeffner().open(...)``
        return isinstance(g, ast.Name) and "oeffner" in g.id
    return False


def ungeschuetzte_netzaufrufe(quelltext: bytes) -> list:
    """``(Zeile, Funktion)`` jedes Netzaufrufs, um den kein ``try`` mit HTTPException/Exception steht."""
    baum = ast.parse(quelltext)
    eltern: dict = {}
    for n in ast.walk(baum):
        for k in ast.iter_child_nodes(n):
            eltern[k] = n
    erg = []
    for n in ast.walk(baum):
        if not (isinstance(n, ast.Call) and _ist_netzaufruf(n)):
            continue
        gefangen: set = set()
        funktion = ""
        k = n
        while k in eltern:
            p = eltern[k]
            if isinstance(p, ast.Try) and any(k is b for b in p.body):
                for h in p.handlers:
                    gefangen |= _handlernamen(h)
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funktion = p.name
                break
            k = p
        if not (gefangen & _ALLES):
            erg.append((n.lineno, funktion))
    return erg


class WaechterTests(unittest.TestCase):

    def test_gegenprobe_erkennt_einen_ungeschuetzten_aufruf(self):
        schlecht = b"""
import urllib.request, urllib.error
def a(u):
    try:
        with urllib.request.urlopen(u) as r:
            return r.read()
    except (urllib.error.URLError, OSError):
        return b""
def b(u):
    try:
        with urllib.request.urlopen(u) as r:
            return r.read()
    except Exception:
        return b""
"""
        self.assertEqual([(5, "a")], ungeschuetzte_netzaufrufe(schlecht))

    def test_jeder_netzaufruf_ist_geschuetzt_oder_begruendet_ausgenommen(self):
        dateien = [PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py",
                   *sorted(p for p in (PROJEKT / "ps5_validator").rglob("*.py") if "__pycache__" not in p.parts)]
        offen = []
        gesehen_ausnahmen = set()
        for pfad in dateien:
            rel = pfad.relative_to(PROJEKT).as_posix()
            for zeile, funktion in ungeschuetzte_netzaufrufe(pfad.read_bytes()):
                if (rel, funktion) in AUFRUFER_FAENGT_ALLES:
                    gesehen_ausnahmen.add((rel, funktion))
                else:
                    offen.append("%s:%d (%s)" % (rel, zeile, funktion))
        self.assertEqual([], offen, "Netzaufruf ohne HTTPException-Schutz (http.client.HTTPException ist kein OSError)")
        veraltet = sorted(AUFRUFER_FAENGT_ALLES - gesehen_ausnahmen)
        self.assertEqual([], veraltet, "Ausnahme ohne Netzaufruf mehr - aus der Liste streichen")


if __name__ == "__main__":
    unittest.main()
