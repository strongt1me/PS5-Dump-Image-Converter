"""Liest VERSION_FILE_URI aus der PS5-Systemdatenbank app.db.

Die Datenbank liegt auf der Konsole unter
``/system_data/priv/mms/app.db`` und wird per FTP geholt.
Um wiederholte Downloads in derselben Sitzung zu vermeiden,
wird das Ergebnis pro Sitzung im Arbeitsspeicher gehalten.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Sitzungs-Cache: Adresse+Port → {TITLE_ID: VERSION_FILE_URI}
_CACHE_SPERRE: threading.Lock = threading.Lock()
_CACHE: dict[str, dict[str, str]] = {}

_FERN_PFAD = "/system_data/priv/mms/app.db"


def _cache_schlussel(adresse: str, port: int) -> str:
    return "%s:%d" % (adresse.strip(), port)


def version_uri_lesen(title_id: str, adresse: str, port: int = 2121,
                      zeit: float = 30.0) -> str:
    """Gibt die VERSION_FILE_URI fuer ``title_id`` aus der app.db zurueck.

    Beim ersten Aufruf fuer eine Konsole wird ``app.db`` vollstaendig
    heruntergeladen und im Sitzungs-Cache gehalten.  Folgeaufrufe
    sind rein lokal.

    Args:
        title_id: Spiel-ID (z. B. ``PPSA12345``), Gross- oder Kleinschreibung.
        adresse:  IP-Adresse der PS5.
        port:     FTP-Port (Standard: 2121).
        zeit:     Zeitgrenze fuer Verbindung und Uebertragung in Sekunden.

    Returns:
        URL-String oder leerer String, wenn nicht vorhanden.

    Raises:
        Exception: FTP-Fehler oder SQLite-Fehler.
    """
    tid = title_id.strip().upper()
    schluessel = _cache_schlussel(adresse, port)

    with _CACHE_SPERRE:
        if schluessel in _CACHE:
            return _CACHE[schluessel].get(tid, "")

    # Noch nicht im Cache: app.db laden und vollstaendig einlesen.
    db_inhalt = _app_db_laden(adresse, port, zeit)
    mapping = _app_db_auslesen(db_inhalt)

    with _CACHE_SPERRE:
        # Nur schreiben, wenn ein anderer Faden nicht schneller war.
        if schluessel not in _CACHE:
            _CACHE[schluessel] = mapping

    return mapping.get(tid, "")


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _app_db_laden(adresse: str, port: int, zeit: float) -> bytes:
    """Laedt ``app.db`` per FTP und gibt den Inhalt als Bytes zurueck."""
    from ps5_validator.utils import konsole_ftp  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "app.db"
        verbindung = konsole_ftp.verbinden(adresse, port, zeit=zeit)
        try:
            ok = konsole_ftp.datei_holen(verbindung, _FERN_PFAD, ziel)
        finally:
            konsole_ftp.schliessen(verbindung)
        if not ok:
            raise RuntimeError("app.db nicht auf der Konsole gefunden: %s" % _FERN_PFAD)
        return ziel.read_bytes()


def _app_db_auslesen(db_inhalt: bytes) -> dict[str, str]:
    """Liest TITLE_ID → VERSION_FILE_URI aus einem SQLite-Dump."""
    mapping: dict[str, str] = {}
    if not db_inhalt:
        return mapping
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_pfad = tmp.name
        tmp.write(db_inhalt)

    try:
        con = sqlite3.connect(tmp_pfad)
        try:
            tabellen = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "tbl_appbrowse" in tabellen:
                cur = con.execute(
                    "SELECT TITLE_ID, VERSION_FILE_URI FROM tbl_appbrowse"
                    " WHERE VERSION_FILE_URI IS NOT NULL AND VERSION_FILE_URI != ''"
                )
                for zeile in cur:
                    tid = str(zeile[0]).strip().upper()
                    uri = str(zeile[1]).strip()
                    if tid and uri:
                        mapping[tid] = uri
            if "tbl_contentinfo" in tabellen:
                # Neuere Firmware: die Adresse steckt im JSON-Feld AppInfoJson.
                for tid_roh, roh in con.execute(
                        "SELECT titleId, AppInfoJson FROM tbl_contentinfo"
                        " WHERE AppInfoJson LIKE '%VERSION_FILE_URI%'"):
                    try:
                        uri = str(json.loads(roh).get("VERSION_FILE_URI", "") or "").strip()
                    except (ValueError, TypeError, AttributeError):
                        continue
                    tid = str(tid_roh or "").strip().upper()
                    if tid and uri:
                        mapping.setdefault(tid, uri)
        finally:
            con.close()
    except sqlite3.Error as fehler:
        logger.debug("app.db Lesefehler: %s", fehler)
    finally:
        try:
            Path(tmp_pfad).unlink()
        except OSError:
            pass

    logger.debug("app.db: %d Eintraege gelesen", len(mapping))
    return mapping
