# -*- coding: utf-8 -*-
"""Netzzugriffe der Update-Downloads, die auf ABBRECHEN sofort reagieren und ihren Stand zeigen.

Gemessen am 08.11.2026 an einem lokalen Langsam-Server (``tests/test_netz_abbruch.py`` stellt ihn nach): Bei einer
Leitung von rund 40 KB/s kam die erste Fortschrittsmeldung erst nach 26 s, und ABBRECHEN wirkte erst nach 21 s -
``antwort.read(1 MiB)`` blockiert, bis das ganze Megabyte da ist. Wartete der Server mit der Antwort (Verbindungsaufbau,
Kopfzeilen), liess sich der Aufruf von ``urlopen`` gar nicht unterbrechen; schwieg er mitten im Strom, endete der Lauf
erst nach der 30-s-Zeitgrenze - und als Netzfehler statt als Abbruch.

Dieses Modul behebt das an drei Stellen:

* :func:`oeffnen` ruft das (blockierende) Oeffnen in einem Hilfsfaden auf und wartet abbrechbar darauf.
* :func:`stueck_lesen` liest hoechstens ein Stueck, das gerade da ist (``read1``), statt auf ein volles Megabyte zu
  warten - so kommt der Fortschritt von der ersten Sekunde an.
* :func:`wache` trennt bei Abbruch die Verbindung (``shutdown`` des Sockets), damit auch ein **schweigender** Server das
  blockierende Lesen nicht festhaelt. Kurze Zeitgrenzen am Socket taugen dafuer nicht: Nach dem ersten Timeout
  verweigert Python jedes weitere Lesen ("cannot read from timed out object").

:func:`schlafen` ist ein ``time.sleep``, das den Abbruch alle 0,2 s ansieht (die Wartezeiten zwischen den Versuchen).

Reine Logik ohne Oberflaeche. Die Fenster rufen die Lader im Faden und zeigen ``geladen`` im Takt.
"""
from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
from typing import Any, Callable, Iterator

#: Groesse eines Lesestuecks. ``read1`` liefert, was schon da ist (bei TLS ein Datensatz, hoechstens 16 KiB).
STUECK = 64 * 1024
#: Takt, in dem auf Abbruch gewartet wird.
_TAKT = 0.2


def schlafen(sekunden: float, abbruch: Callable[[], bool] | None) -> bool:
    """Wartet ``sekunden``; ``True``, wenn der Abbruch dazwischenkam (dann sofort)."""
    ende = time.monotonic() + max(0.0, sekunden)
    while True:
        if abbruch is not None and abbruch():
            return True
        rest = ende - time.monotonic()
        if rest <= 0:
            return False
        time.sleep(min(_TAKT, rest))


def oeffnen(opener: Callable[[], Any], abbruch: Callable[[], bool] | None,
            bei_abbruch: Callable[[], BaseException]) -> Any:
    """Ruft ``opener()`` (z. B. ``urlopen``) auf und wartet darauf, ohne den Abbruch zu verpassen.

    Der Aufruf selbst laeuft in einem Hilfsfaden. Kommt der Abbruch zuerst, wird ``bei_abbruch()`` geworfen; die Anfrage
    endet im Hintergrund mit ihrer eigenen Zeitgrenze, und ihr Ergebnis wird dann sofort wieder geschlossen.

    Returns:
        Die Antwort von ``opener()``. Dessen Ausnahme wird unveraendert weitergereicht.
    """
    if abbruch is None:
        return opener()
    stand: dict[str, Any] = {}
    sperre = threading.Lock()

    def _lauf() -> None:
        try:
            antwort = opener()
        except BaseException as exc:  # noqa: BLE001 - wird im aufrufenden Faden erneut geworfen
            with sperre:
                stand["fehler"] = exc
            return
        with sperre:
            verwerfen = bool(stand.get("verworfen"))
            if not verwerfen:
                stand["antwort"] = antwort
        if verwerfen:
            _schliessen(antwort)

    faden = threading.Thread(target=_lauf, daemon=True, name="netz-oeffnen")
    faden.start()
    while faden.is_alive():
        faden.join(_TAKT)
        if abbruch():
            with sperre:
                antwort = stand.get("antwort")
                if antwort is None:
                    stand["verworfen"] = True
            if antwort is not None:
                _schliessen(antwort)
            raise bei_abbruch()
    with sperre:
        fehler = stand.get("fehler")
        antwort = stand.get("antwort")
    if fehler is not None:
        raise fehler
    return antwort


def _schliessen(antwort: Any) -> None:
    try:
        antwort.close()
    except Exception:  # noqa: BLE001
        pass


def _trennen(antwort: Any) -> None:
    """Trennt die Verbindung hinter ``antwort`` so, dass ein blockiertes ``recv`` in anderen Faeden sofort endet.

    Gemessen am 08.11.2026 unter Windows: ``shutdown`` **und** ``close`` lassen ein blockiertes ``recv`` haengen
    (``close`` schiebt das eigentliche Schliessen auf, solange ``makefile`` den Socket haelt); erst ``_real_close()``
    befreit den Leser sofort (WinError 10038). Unter Linux und macOS weckt ``shutdown`` den Leser; dort wird nicht
    geschlossen, damit die Dateinummer nicht wiederverwendet wird, waehrend der Leser noch in ``recv`` steht.
    """
    try:
        sock = antwort.fp.raw._sock  # noqa: SLF001 - einziger Weg an den Socket einer urllib-Antwort
    except Exception:  # noqa: BLE001 - Attrappe ohne Socket
        _schliessen(antwort)
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    if os.name == "nt":
        # Fehlt das private _real_close in einer kuenftigen Fassung, bleibt wenigstens close() (schiebt das Schliessen
        # ggf. auf, wirkt dann aber spaetestens mit der Zeitgrenze der Anfrage).
        echt = getattr(sock, "_real_close", None) or sock.close
        try:
            echt()
        except Exception:  # noqa: BLE001
            pass


@contextlib.contextmanager
def wache(antwort: Any, abbruch: Callable[[], bool] | None) -> Iterator[None]:
    """Solange der Block laeuft, trennt ein Hilfsfaden die Verbindung, sobald ``abbruch()`` wahr wird."""
    if abbruch is None:
        yield
        return
    fertig = threading.Event()

    def _lauf() -> None:
        while not fertig.wait(_TAKT):
            if abbruch():
                _trennen(antwort)
                return

    faden = threading.Thread(target=_lauf, daemon=True, name="netz-wache")
    faden.start()
    try:
        yield
    finally:
        fertig.set()


def stueck_lesen(antwort: Any, abbruch: Callable[[], bool] | None, bei_abbruch: Callable[[], BaseException],
                 groesse: int = STUECK) -> bytes:
    """Liest das naechste Stueck der Antwort; ``b""`` heisst Ende.

    Prueft vor dem Lesen den Abbruch. Endet das Lesen mit einer Ausnahme **oder** mit ``b""``, waehrend der Abbruch
    verlangt ist (die :func:`wache` hat die Verbindung getrennt), gilt das als Abbruch und nicht als Netzfehler oder
    als vorzeitiges Ende. Fehlt ``read1`` (Attrappen in Tests), wird ``read`` genommen.
    """
    lesen = getattr(antwort, "read1", None) or antwort.read
    if abbruch is not None and abbruch():
        raise bei_abbruch()
    try:
        block = lesen(groesse)
    except Exception as exc:  # noqa: BLE001 - getrennt: OSError, ValueError (geschlossene Datei), http.client-Fehler
        if abbruch is not None and abbruch():
            raise bei_abbruch() from exc
        raise
    if not block and abbruch is not None and abbruch():
        raise bei_abbruch()
    return block
