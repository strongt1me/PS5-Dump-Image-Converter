"""Sucht die VERSION_FILE_URI einer PS5-Title-ID aus Abbilddateien oder der PS5-Datenbank.

Zwei Wege:
- ``aus_abbild``: Scannt einen Ordner nach .exfat- und PKG/fPKG-Dateien und liest
  param.json ohne vollstaendiges Entpacken.
- ``per_ftp``: Laed app.db von der Konsole und fragt sie ab (ps5_appdb).
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Unterstützte Erweiterungen (alles in Kleinschreibung)
_EXFAT_EXTS  = frozenset({".exfat"})
_PKG_EXTS    = frozenset({".pkg", ".fpkg"})
_PFSC_EXTS   = frozenset({".ffpfsc", ".ffpfs"})


def aus_abbild(title_id: str, ordner: str, mkpfs_dir: str = "") -> str:
    """Sucht VERSION_FILE_URI durch Lesen von param.json aus Abbilddateien.

    Scannt ``ordner`` (nicht rekursiv) nach Abbilddateien, deren Name den
    ``title_id``-String enthaelt, und gibt die erste gefundene URI zurueck.

    Args:
        title_id: PPSA/PPUS/PPJP-ID (Gross-/Kleinschreibung gleichwertig).
        ordner:   Arbeitsordner (z. B. der aktuell geladene Quellordner).
        mkpfs_dir: sys.path-Eintrag der MkPFS-Engine (fuer .ffpfsc/.ffpfs).

    Returns:
        URI-String oder leerer String.
    """
    tid = title_id.strip().upper()
    if not tid or not os.path.isdir(ordner):
        return ""

    try:
        eintraege = os.listdir(ordner)
    except OSError as fehler:
        logger.debug("version_uri_suche.aus_abbild: Listefehler %s: %s", ordner, fehler)
        return ""

    for name in eintraege:
        if tid not in name.upper():
            continue
        pfad = os.path.join(ordner, name)
        if not os.path.isfile(pfad):
            continue
        ext = os.path.splitext(name)[1].lower()
        uri = ""
        if ext in _EXFAT_EXTS:
            uri = _uri_aus_exfat(pfad, mkpfs_dir)
        elif ext in _PKG_EXTS:
            uri = _uri_aus_pkg(pfad)
        elif ext in _PFSC_EXTS:
            uri = _uri_aus_ffpfsc(pfad, mkpfs_dir)
        if uri:
            logger.debug("version_uri_suche: URI aus %s gefunden", name)
            return uri

    return ""


def per_ftp(title_id: str, ps5_ip: str, port: int = 2121,
            zeit: float = 30.0) -> str:
    """Liest VERSION_FILE_URI aus der app.db der PS5.

    Args:
        title_id: PPSA/PPUS/PPJP-ID.
        ps5_ip:   IP-Adresse der Konsole.
        port:     FTP-Port (Standard: 2121).
        zeit:     Zeitgrenze in Sekunden.

    Returns:
        URI-String oder leerer String.  Fehler werden geloggt und nicht
        weitergegeben.
    """
    if not ps5_ip or not ps5_ip.strip():
        return ""
    try:
        from ps5_validator.utils import ps5_appdb  # noqa: PLC0415
        return ps5_appdb.version_uri_lesen(title_id, ps5_ip.strip(), port, zeit)
    except Exception as fehler:  # noqa: BLE001
        logger.debug("version_uri_suche.per_ftp: %s", fehler)
        return ""


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _uri_aus_exfat(pfad: str, mkpfs_dir: str) -> str:
    """Liest versionFileUri aus einer .exfat-Abbild-Datei."""
    try:
        if mkpfs_dir and mkpfs_dir not in __import__("sys").path:
            __import__("sys").path.insert(0, mkpfs_dir)
        from mkpfs.exfat import ExfatReader  # noqa: PLC0415  # type: ignore[import-not-found]
        from ps5_validator.utils.exfat_gezielt import GezielterZugriff  # noqa: PLC0415
        with open(pfad, "rb") as fh:
            leser = ExfatReader(fh)
            gz = GezielterZugriff(leser)
            eintrag = gz.suchen("sce_sys", "param.json")
            if eintrag is None:
                return ""
            rohe = gz.lesen(eintrag)
            if not rohe:
                return ""
            daten = json.loads(rohe.decode("utf-8", errors="replace"))
            return str(daten.get("versionFileUri", "") or "").strip()
    except Exception as fehler:  # noqa: BLE001
        logger.debug("_uri_aus_exfat %s: %s", os.path.basename(pfad), fehler)
        return ""


def _uri_aus_pkg(pfad: str) -> str:
    """Liest versionFileUri aus einer PKG- oder fPKG-Datei."""
    try:
        from ps5_validator.utils import pkg_reader  # noqa: PLC0415
        info = pkg_reader.read_pkg(pfad)
        daten = pkg_reader.try_read_param_json(pfad, info)
        if not isinstance(daten, dict):
            return ""
        return str(daten.get("versionFileUri", "") or "").strip()
    except Exception as fehler:  # noqa: BLE001
        logger.debug("_uri_aus_pkg %s: %s", os.path.basename(pfad), fehler)
        return ""


def _uri_aus_ffpfsc(pfad: str, mkpfs_dir: str) -> str:
    """Liest versionFileUri aus einer .ffpfsc- oder .ffpfs-Datei."""
    try:
        import sys  # noqa: PLC0415
        if mkpfs_dir and mkpfs_dir not in sys.path:
            sys.path.insert(0, mkpfs_dir)
        from mkpfs.exfat import ExfatReader  # noqa: PLC0415  # type: ignore[import-not-found]
        from mkpfs.pfs import open_inner_file_view  # noqa: PLC0415  # type: ignore[import-not-found]
        from ps5_validator.utils.exfat_gezielt import GezielterZugriff  # noqa: PLC0415

        # Zuerst das Abbild selbst als flaches PFS/exFAT versuchen
        try:
            from mkpfs.pfs import open_virtual_pfs_reader as _ovpr  # noqa: PLC0415  # type: ignore[import-not-found]
            with open(pfad, "rb") as fh:
                leser = _ovpr(fh)
                if leser is not None:
                    gz = GezielterZugriff(leser)
                    eintrag = gz.suchen("sce_sys", "param.json")
                    if eintrag is not None:
                        rohe = gz.lesen(eintrag)
                        if rohe:
                            return str(json.loads(rohe.decode("utf-8", errors="replace")
                                                  ).get("versionFileUri", "") or "").strip()
        except Exception:  # noqa: BLE001
            pass

        inner_view_info = open_inner_file_view(__import__("pathlib").Path(pfad))
        if inner_view_info is None:
            return ""
        virtual_fh, backing_fh, _ = inner_view_info
        try:
            try:
                leser = ExfatReader(virtual_fh)
                gz = GezielterZugriff(leser)
                eintrag = gz.suchen("sce_sys", "param.json")
                if eintrag is not None:
                    rohe = gz.lesen(eintrag)
                    if rohe:
                        return str(json.loads(rohe.decode("utf-8", errors="replace")
                                              ).get("versionFileUri", "") or "").strip()
            except Exception:  # noqa: BLE001
                pass
        finally:
            close_fn = getattr(virtual_fh, "close", None)
            if callable(close_fn):
                close_fn()
            backing_fh.close()
    except Exception as fehler:  # noqa: BLE001
        logger.debug("_uri_aus_ffpfsc %s: %s", os.path.basename(pfad), fehler)
    return ""
