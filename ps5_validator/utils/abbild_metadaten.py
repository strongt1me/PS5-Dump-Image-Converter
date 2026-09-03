# -*- coding: utf-8 -*-
"""Liest Spielmetadaten und Titelbild aus einem Abbild - ohne es zu entpacken.

Achter Schnitt der Trennung, und der groesste: vierzehn Methoden mit
zusammen rund 1080 Zeilen - seit dem 03.09.2026 rund 106 Zeilen weniger,
weil die param.json-Auswertung nur noch einmal dasteht (siehe
``_meta_from_param_json_payload``). Sie beantworten eine Frage - **was steckt in
diesem Abbild** - und beantworten sie fuer jedes Format, das das Programm
kennt: Dump-Ordner, ``.ffpkg`` (ueber Mustersuche oder ueber UFS2Tool),
``.ffpfsc`` (ueber den virtuellen PFS-Leser), exFAT und PFS.

**Warum so gross geschnitten.** Ein kleinerer Schnitt war entworfen und
verworfen: Er haette nur die sechs ``_extract_meta_*``-Methoden genommen
und ``_read_game_meta`` im Monolithen gelassen. Dann braeuchte das Modul
den Leser als Rueckruf und der Monolith die Firmware-Auswertung aus dem
Modul - ein Ringschluss ueber die Nahtstelle. Mit den vier Lesern
zusammen ist es ein geschlossener Kreis: **acht** Nahtstellen statt elf,
und keine davon zeigt zurueck.

**Warum eine Klasse und keine freien Funktionen.** Die vierzehn Methoden
rufen einander vierundzwanzig Mal ueber ``self``. Als freie Funktionen
haette jeder dieser Aufrufe umgeschrieben werden muessen - bei 1080
Zeilen ist das die Sorte Aenderung, bei der ein Tippfehler erst Monate
spaeter auffaellt. So wandern die Ruempfe **woertlich**.

**Warum die inneren Namen englisch geblieben sind.** Aus demselben Grund:
``self._append_to_log`` und ``self._t`` heissen im Rumpf weiter so, damit
kein Rumpf angefasst werden musste. Die Schnittstelle nach aussen - der
Erzeuger - ist deutsch benannt; dort steht, was wirklich hereingereicht
wird.

**Was draussen bleibt.** ``_extract_embedded_mkpfs`` und
``_extract_ufs2tool`` liegen seit dem siebten Schnitt in
:mod:`ps5_validator.utils.werkzeuge_bereitstellen`; hier kommt nur der
fertige Pfad herein. ``_meta_aus_sfo`` bleibt im Monolithen - es haengt an
der Anzeige - und wird gereicht.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ps5_validator.utils.nahtstellen import (Melder, Textquelle,
                                             schluessel_zeigen, stumm)
from ps5_validator.utils.plattform import ist_administrator, prozess_flags

try:
    from PIL import Image
except ImportError:  # pragma: no cover - ohne Pillow gibt es keine Bilder
    Image = None  # type: ignore[assignment]

logger = logging.getLogger("PS5Converter.utils.abbild_metadaten")

#: Die Title-ID-Formen, die auf einer PS5 vorkommen. Sie stehen hier und
#: werden vom Monolithen von hier geholt - doppelt gefuehrt liefen sie
#: auseinander.
_TITLE_ID_PATTERN = (r"PPSA\d{5}|PPUS\d{5}|PPJP\d{5}|CUSA\d{5}|PUSA\d{5}"
                     r"|PCJS\d{5}|PCAS\d{5}|ECAS\d{5}")
_TITLE_ID_RE = re.compile(rf"(?<![A-Z0-9])({_TITLE_ID_PATTERN})(?![A-Z0-9])")


class Metadatenleser:
    """Liest Metadaten aus einem Abbild.

    Args:
        mkpfs_ordner: Der ``sys.path``-Eintrag der bereitgestellten
            MkPFS-Engine.
        melden: Nimmt Protokollzeilen entgegen.
        text: Uebersetzt Meldungsschluessel.
        sfo_lesen: Liest eine ``param.sfo`` roh aus.
        voll_sfo_lesen: Die ausfuehrliche SFO-Auswertung des Monolithen
            (``_meta_aus_sfo``).
        pfs_leser_oeffnen: Oeffnet den virtuellen PFS-Leser.
        dokan_vorhanden: Ob der Dokan-Treiber da ist.
        ufs2tool_pfad: Liefert den Pfad zu UFS2Tool.
        vorschau_sperre: Verhindert, dass zwei Vorschauen gleichzeitig
            einhaengen. Darf fehlen.
    """

    def __init__(self, *, mkpfs_ordner: str = "",
                 melden: Melder | None = None,
                 text: Textquelle | None = None,
                 sfo_lesen: Callable[[bytes], dict] | None = None,
                 voll_sfo_lesen: Callable[..., Any] | None = None,
                 pfs_leser_oeffnen: Callable[..., Any] | None = None,
                 dokan_vorhanden: Callable[[], Any] | None = None,
                 ufs2tool_pfad: Callable[[], str] | None = None,
                 vorschau_sperre: Any = None) -> None:
        self.mkpfs_dir = mkpfs_ordner
        self._append_to_log = melden or stumm
        self._t = text or schluessel_zeigen
        self._sfo_leser = sfo_lesen or (lambda _roh: {})
        self._meta_aus_sfo = voll_sfo_lesen or (lambda *a, **k: None)
        self._open_virtual_pfs_reader = pfs_leser_oeffnen
        self._find_dokan_driver = dokan_vorhanden or (lambda: None)
        self._extract_ufs2tool = ufs2tool_pfad or (lambda: "")
        self._ffpkg_preview_lock = vorschau_sperre

    @staticmethod
    def _region_from_title_id(title_id: str) -> str:
        """Leitet die Region aus dem Titel-ID-Präfix ab.

        PS5-Titel-IDs folgen dem Schema PPSA/PPUS/PPJP + Nummer.
        """
        tid = (title_id or "").upper().strip()
        # Muss jedes von _is_valid_title_id akzeptierte Präfix abdecken, sonst
        # zeigt die Infobox für eine gültige Title-ID fälschlich "–" als Region.
        mapping = {
            "PPSA": "Europa",
            "PPSS": "Europa",
            "ECAS": "Europa",
            "PPUS": "USA",
            "CUSA": "USA",
            "PUSA": "USA",
            "PPJP": "Japan",
            "PCJS": "Japan",
            "PCAS": "Asien",
        }
        for prefix, region in mapping.items():
            if tid.startswith(prefix):
                return region
        return "–"

    @staticmethod
    def _normalize_required_firmware(value: object) -> str:
        """Normalisiert rohe Firmware-Angaben aus param.json oder param.sfo."""
        if value is None or isinstance(value, (dict, list, tuple, set)):
            return "–"

        # Eine param.sfo liefert SYSTEM_VER als Rohbytes, nicht als Zahl.
        # Ohne diesen Zweig landeten sie in str() und kamen als
        # "b'\x00\x00u\x01'" in der Infobox an - am 29.08.2026 an
        # einem PS4-Paket gesehen. Die Bytes stehen little-endian.
        if isinstance(value, (bytes, bytearray)):
            if not value or len(value) > 8:
                return "–"
            value = int.from_bytes(bytes(value), "little")

        if isinstance(value, int):
            if value < 0:
                return "–"
            hex_head = f"{value:08X}"[-8:]
            if hex_head.startswith("00") and len(hex_head) == 8 and any(ch != "0" for ch in hex_head[2:4]):
                hex_head = hex_head[1:] + "0"
            return ".".join(hex_head[i:i + 2] for i in range(0, 8, 2))

        raw = str(value).strip()
        if not raw or raw in {"–", "-", "Unbekannt", "�"}:
            return "–"

        version_match = re.search(r"\b\d{1,2}\.\d{2}\.\d{2}\.\d{2}\b", raw)
        if version_match:
            return version_match.group(0)

        version_match = re.search(r"\b\d{1,2}\.\d{2}\.\d{2}\b", raw)
        if version_match:
            return version_match.group(0)

        version_match = re.search(r"\b\d{1,2}\.\d{2}\b", raw)
        if version_match:
            return version_match.group(0)

        # Das Praefix "0x" zuerst weg. Vorher entfernte die Zeichenklasse nur das
        # "x" - die fuehrende 0 blieb stehen und verschob alles um eine Stelle:
        # Aus 0x1001000000000000 (also 10.01) wurde "01.00.10.00". Die frueher
        # hier stehende Rotation bei fuehrenden Nullen war der Ausgleich dafuer
        # und ging nur bei einstelliger Hauptversion auf (0x0900 -> 09.00),
        # nicht bei zweistelliger.
        #
        # Die Ziffern sind BCD: Die Hex-ZEICHEN sind die gedruckten Ziffern,
        # keine Hexzahl - 0x1270... heisst 12.70, nicht 4720.
        ohne_praefix = re.sub(r"^0[xX]", "", raw)
        hex_chars = re.sub(r"[^0-9A-Fa-f]", "", ohne_praefix)
        if len(hex_chars) >= 8:
            hex_head = hex_chars[:8].upper()
            return ".".join(hex_head[i:i + 2] for i in range(0, 8, 2))

        return raw

    @classmethod
    def _extract_required_firmware_value(cls, payload: object) -> str:
        """Sucht rekursiv nach einer Firmware-Angabe in JSON-ähnlichen Daten."""
        target_keys = {
            "requiredfirmware",
            "required_firmware",
            "requiredsystemsoftwareversion",
            "requiredsystemversion",
            "systemsoftwareversion",
            "systemversion",
            "system_ver",
            "ps5_system_ver",
            "minimumfirmware",
            "minimumfirmwareversion",
            "targetsystemsoftwareversion",
        }
        queue: list[object] = [payload]
        visited = 0
        while queue and visited < 120:
            visited += 1
            current = queue.pop(0)
            if isinstance(current, dict):
                for key, value in current.items():
                    key_norm = str(key).strip().lower().replace(" ", "").replace("-", "").replace(".", "")
                    if key_norm in target_keys:
                        fw = cls._normalize_required_firmware(value)
                        if fw != "–":
                            return fw
                for value in current.values():
                    if isinstance(value, (dict, list, tuple)):
                        queue.append(value)
            elif isinstance(current, (list, tuple)):
                for value in current:
                    if isinstance(value, (dict, list, tuple)):
                        queue.append(value)
        return "–"

    def _extract_meta_from_ffpkg_file(self, src: str) -> dict[str, str]:
        """Extrahiert Title-ID/Version heuristisch direkt aus einer .ffpkg-Datei.

        Dieser schnelle Muster-Scan ist nur ein Fallback, wenn der strukturierte
        read-only UFS2Tool-/Dokan-Pfad nicht verfügbar ist.
        """
        meta: dict[str, str] = {
            "title": "–",
            "title_id": "–",
            "version": "–",
            "required_firmware": "–",
            "region": "–",
            "category": "–",
            "publisher": "–",
        }
        if not src or not os.path.isfile(src) or not src.lower().endswith(".ffpkg"):
            return meta

        title_id_re = _TITLE_ID_RE
        content_id_re = re.compile(
            rf"[A-Z]{{2}}\d{{4}}-({_TITLE_ID_PATTERN})_00-[A-Z0-9]{{8,32}}"
        )
        version_re = re.compile(r"(?<!\d)(\d{2}\.\d{3}\.\d{3})(?!\d)")
        labeled_version_re = re.compile(
            r"(?:APP_VER|VERSION|CONTENT_VER|MASTER_VERSION|"
            r"appVer|contentVersion|masterVersion)"
            r"\s*[=:]\s*['\"]?(\d{2}\.\d{3}\.\d{3})"
        )
        scan_chunks: list[bytes] = []

        def _iter_sample_offsets(file_size: int) -> list[int]:
            window = 256 * 1024
            offsets: list[int] = [0]
            max_front = min(file_size, 64 * 1024 * 1024)
            step = 2 * 1024 * 1024
            pos = step
            while pos < max_front:
                offsets.append(pos)
                pos += step
            if file_size > window:
                offsets.append(max(0, file_size - window))

            unique: list[int] = []
            seen: set[int] = set()
            for off in offsets:
                off = max(0, min(off, max(0, file_size - window)))
                if off in seen:
                    continue
                seen.add(off)
                unique.append(off)
            return unique

        def _scan_text(text: str) -> None:
            if not text:
                return
            if meta["title_id"] == "–":
                match = title_id_re.search(text)
                if match is None:
                    content_match = content_id_re.search(text)
                    if content_match is not None:
                        meta["title_id"] = content_match.group(1).upper()
                else:
                    meta["title_id"] = match.group(1).upper()
                if meta["title_id"] != "–":
                    meta["region"] = self._region_from_title_id(meta["title_id"])
            if meta["version"] == "–":
                match = labeled_version_re.search(text)
                if match is None:
                    match = version_re.search(text)
                if match is not None:
                    meta["version"] = match.group(1)

        try:
            file_size = os.path.getsize(src)
            with open(src, "rb") as fh:
                for offset in _iter_sample_offsets(file_size):
                    fh.seek(offset)
                    chunk = fh.read(256 * 1024)
                    if chunk:
                        scan_chunks.append(chunk)
        except Exception as exc:
            logger.debug("FFPKG-Metascan fehlgeschlagen: %s", exc)
            return meta

        for chunk in scan_chunks:
            text_ascii = chunk.decode("latin-1", "ignore")
            _scan_text(text_ascii)
            if meta["title_id"] == "–" or meta["version"] == "–":
                text_no_nul = chunk.replace(b"\x00", b"").decode("latin-1", "ignore")
                _scan_text(text_no_nul)
            if meta["title_id"] == "–" or meta["version"] == "–":
                try:
                    text_utf16 = chunk.decode("utf-16-le", "ignore")
                except Exception:
                    text_utf16 = ""
                _scan_text(text_utf16)
            if meta["title_id"] != "–" and meta["version"] != "–":
                break

        return meta

    def _extract_meta_from_ffpkg_ufs2(
        self, src: str
    ) -> tuple[dict[str, str], Image.Image | None]:
        """Liest Spielmetadaten aus einem UFS2-.ffpkg über einen read-only Mount."""
        empty_meta: dict[str, str] = {
            "title": "–", "title_id": "–", "version": "–", "required_firmware": "–",
            "region": "–", "category": "–", "publisher": "–",
        }
        if (
            not src
            or not os.path.isfile(src)
            or not src.lower().endswith(".ffpkg")
            or not ist_administrator()
            or not self._find_dokan_driver()
        ):
            return empty_meta, None

        lock = getattr(self, "_ffpkg_preview_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._ffpkg_preview_lock = lock

        with lock:
            mount_proc: subprocess.Popen[str] | None = None
            drive = ""
            mounted = False
            try:
                exe = self._extract_ufs2tool()
                import ctypes as _ct

                drives_bitmask = _ct.windll.kernel32.GetLogicalDrives()
                for idx in range(25, 3, -1):
                    if not (drives_bitmask & (1 << idx)):
                        drive = chr(65 + idx) + ":"
                        break
                if not drive:
                    return empty_meta, None

                mount_proc = subprocess.Popen(
                    [exe, "mount_udf", "-o", "ro", src, drive],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="mbcs",
                    errors="replace",
                    **prozess_flags(),
                )
                for _ in range(40):
                    if mount_proc.poll() is not None:
                        break
                    if os.path.exists(drive + "\\"):
                        mounted = True
                        break
                    time.sleep(0.25)
                if not mounted:
                    return empty_meta, None

                meta, cover = self._read_game_meta_and_cover(drive + "\\")
                return meta, cover
            except Exception as exc:
                logger.debug("Strukturierter UFS2-Metadaten-Read fehlgeschlagen: %s", exc)
                return empty_meta, None
            finally:
                if mount_proc is not None:
                    try:
                        mount_proc.terminate()
                        mount_proc.wait(timeout=10)
                    except Exception:
                        try:
                            mount_proc.kill()
                        except Exception:
                            pass
                try:
                    if mounted and drive and os.path.exists(drive + "\\"):
                        subprocess.run(
                            ["mountvol", drive + "\\", "/D"],
                            timeout=10,
                            capture_output=True,
                            **prozess_flags(),
                        )
                except Exception:
                    pass

    def _read_game_meta(self, src: str, deep_scan: bool = True) -> dict:
        """Liest Spielmetadaten aus param.json oder param.sfo.

        Sucht zuerst nach param.json, dann als Fallback nach param.sfo.
        Gibt ein normalisiertes Dict mit den Schlüsseln
        title, title_id, version, required_firmware, region, category, publisher zurück.

        Args:
            src: Pfad zum Quellordner.
            deep_scan: Wenn True, werden auch Unterordner-Fallbacks genutzt.
        """
        meta: dict[str, str] = {
            "title":     "–",
            "title_id":  "–",
            "version":   "–",
            "required_firmware": "–",
            "region":    "–",
            "category":  "–",
            "publisher": "–",
        }

        # --- Schnellpfad: bekannte Standard-Positionen direkt prüfen ---
        json_path: str | None = None
        _json_candidates = [
            os.path.join(src, "param.json"),
            os.path.join(src, "sce_sys", "param.json"),
        ]
        # Eine Ebene tiefer: src/GAMEID/sce_sys/param.json
        if deep_scan:
            try:
                for _entry in os.listdir(src):
                    _json_candidates.append(os.path.join(src, _entry, "sce_sys", "param.json"))
                    _json_candidates.append(os.path.join(src, _entry, "param.json"))
                    if len(_json_candidates) > 22:
                        break
            except OSError:
                pass
        for _cand in _json_candidates:
            if os.path.isfile(_cand):
                json_path = _cand
                break

        # Bringt der Ordner die AMPR-Emulation mit? Hier gesetzt und nicht am
        # Ende: Der param.json-Zweig kehrt mittendrin zurueck, und die Angabe
        # soll auf jedem Weg mitkommen. Gesucht wird neben der gefundenen
        # param.json, nicht im Wurzelordner - der kann mehrere Spiele halten.
        _spielordner = (os.path.dirname(os.path.dirname(json_path))
                        if json_path else src)
        if _spielordner and os.path.isdir(_spielordner):
            meta["ampr_emu"] = self._t(
                "info_popup.meta.ampr_emu_ja"
                if os.path.isfile(os.path.join(_spielordner, "fakelib", "libSceAmpr.sprx"))
                else "info_popup.meta.ampr_emu_nein")
        # --- Fallback: nur sce_sys-Unterordner bis Tiefe 2 prüfen (kein vollständiger Scan) ---
        if deep_scan and not json_path:
            try:
                for _lvl1 in os.listdir(src):
                    _lvl1_path = os.path.join(src, _lvl1)
                    if not os.path.isdir(_lvl1_path):
                        continue
                    # Direkt: src/sce_sys/param.json oder src/GAMEID/sce_sys/param.json
                    for _sub in ("", "sce_sys"):
                        _p = (
                            os.path.join(_lvl1_path, _sub, "param.json")
                            if _sub
                            else os.path.join(_lvl1_path, "param.json")
                        )
                        if os.path.isfile(_p):
                            json_path = _p
                            break
                    if json_path:
                        break
                    # Tiefe 2: src/GAMEID/SUBDIR/sce_sys/param.json
                    try:
                        for _lvl2 in os.listdir(_lvl1_path):
                            _p2 = os.path.join(_lvl1_path, _lvl2, "sce_sys", "param.json")
                            if os.path.isfile(_p2):
                                json_path = _p2
                                break
                    except OSError:
                        pass
                    if json_path:
                        break
            except OSError:
                pass

        if json_path:
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # Eine param.json, die kein Objekt ist, ist unbrauchbar - dann
                # soll der Weg auf die param.sfo fallen und nicht mit leeren
                # Feldern zurueckkehren. Bis zum 03.09.2026 erledigte das der
                # AttributeError von ``data.get()``; seit die Auswertung
                # nebenan sitzt und einen Nicht-Dict abfaengt, muss es
                # dastehen.
                if not isinstance(data, dict):
                    raise ValueError("param.json enthaelt kein Objekt")
                meta.update(self._meta_from_param_json_payload(data))
                return meta
            except Exception:
                pass  # Fallback auf SFO

        # --- Fallback: param.sfo – nur sce_sys-Unterordner prüfen (kein vollständiger Scan) ---
        sfo_path: str | None = None
        _sfo_candidates = [
            os.path.join(src, "param.sfo"),
            os.path.join(src, "sce_sys", "param.sfo"),
        ]
        if deep_scan:
            try:
                for _entry in os.listdir(src):
                    _sfo_candidates.append(os.path.join(src, _entry, "sce_sys", "param.sfo"))
                    _sfo_candidates.append(os.path.join(src, _entry, "param.sfo"))
                    if len(_sfo_candidates) > 22:
                        break
            except OSError:
                pass
        for _sc in _sfo_candidates:
            if os.path.isfile(_sc):
                sfo_path = _sc
                break
        # Letzter Fallback: Tiefe-2-Scan nur in sce_sys-Unterordnern
        if deep_scan and not sfo_path:
            try:
                for _lvl1 in os.listdir(src):
                    _lvl1_path = os.path.join(src, _lvl1)
                    if not os.path.isdir(_lvl1_path):
                        continue
                    _p = os.path.join(_lvl1_path, "sce_sys", "param.sfo")
                    if os.path.isfile(_p):
                        sfo_path = _p
                        break
                    try:
                        for _lvl2 in os.listdir(_lvl1_path):
                            _p2 = os.path.join(_lvl1_path, _lvl2, "sce_sys", "param.sfo")
                            if os.path.isfile(_p2):
                                sfo_path = _p2
                                break
                    except OSError:
                        pass
                    if sfo_path:
                        break
            except OSError:
                pass

        if sfo_path:
            try:
                with open(sfo_path, "rb") as fh:
                    sfo_data = fh.read()
                sfo = self._sfo_leser(sfo_data)
                if sfo:
                    meta.update(self._meta_aus_sfo(sfo))
            except Exception as exc:
                logger.debug("Cover-Bild aus SFO konnte nicht geladen werden: %s", exc)

        # Letzter Fallback: Region aus Titel-ID ableiten wenn noch leer
        if meta.get("region", "–") == "–" and meta.get("title_id", "–") != "–":
            meta["region"] = self._region_from_title_id(meta["title_id"])

        return meta

    def _load_cover_image(self, src: str, deep_scan: bool = True) -> Image.Image | None:
        """Lädt icon0.png aus dem Quellordner – schnell via direkter Pfad-Prüfung.
        Prüft zuerst bekannte Standardpfade (sce_sys/icon0.png), dann erst os.walk.
        Args:
            src: Pfad zum Quellordner oder sce_sys-Verzeichnis.
        Returns:
            PIL Image oder None wenn nicht gefunden.
        """
        # --- Schnellpfad: bekannte Standard-Positionen direkt prüfen ---
        _candidates = [
            os.path.join(src, "icon0.png"),
            os.path.join(src, "sce_sys", "icon0.png"),
        ]
        # Auch eine Ebene tiefer: src/GAMEID/sce_sys/icon0.png
        if deep_scan:
            try:
                for entry in os.listdir(src):
                    sub = os.path.join(src, entry, "sce_sys", "icon0.png")
                    _candidates.append(sub)
                    sub2 = os.path.join(src, entry, "icon0.png")
                    _candidates.append(sub2)
                    # Maximal 20 Einträge für den Schnellpfad
                    if len(_candidates) > 22:
                        break
            except OSError:
                pass
        for candidate in _candidates:
            if os.path.isfile(candidate):
                try:
                    img = Image.open(candidate)
                    img.load()  # Sofort in RAM laden (verhindert späteres I/O)
                    return img.convert("RGBA")
                except Exception:
                    return None
        # --- Fallback: nur sce_sys-Unterordner bis Tiefe 2 prüfen (kein vollständiger Scan) ---
        if deep_scan:
            try:
                for _lvl1 in os.listdir(src):
                    _lvl1_path = os.path.join(src, _lvl1)
                    if not os.path.isdir(_lvl1_path):
                        continue
                    # src/GAMEID/sce_sys/icon0.png und src/GAMEID/icon0.png
                    for _sub_path in (
                        os.path.join(_lvl1_path, "sce_sys", "icon0.png"),
                        os.path.join(_lvl1_path, "icon0.png"),
                    ):
                        if os.path.isfile(_sub_path):
                            try:
                                img = Image.open(_sub_path)
                                img.load()
                                return img.convert("RGBA")
                            except Exception:
                                return None
                    # Tiefe 2: src/GAMEID/SUBDIR/sce_sys/icon0.png
                    try:
                        for _lvl2 in os.listdir(_lvl1_path):
                            _p2 = os.path.join(_lvl1_path, _lvl2, "sce_sys", "icon0.png")
                            if os.path.isfile(_p2):
                                try:
                                    img = Image.open(_p2)
                                    img.load()
                                    return img.convert("RGBA")
                                except Exception:
                                    return None
                    except OSError:
                        pass
            except OSError:
                pass

        # Letzter Fallback: gezielte rekursive Suche. Das ist wichtig für
        # entpackte Container, deren Struktur tiefer verschachtelt ist als die
        # üblichen 1-2 Ebenen aus den Schnellpfaden.
        if deep_scan:
            try:
                _seen_dirs = 0
                for _root, _dirs, _files in os.walk(src):
                    _seen_dirs += 1
                    if _seen_dirs > 300:
                        break
                    _root_low = _root.replace("\\", "/").lower()
                    for _fn in _files:
                        if _fn.lower() != "icon0.png":
                            continue
                        # Bevorzugt Treffer innerhalb von sce_sys.
                        if "sce_sys" not in _root_low and _seen_dirs < 300:
                            continue
                        _candidate = os.path.join(_root, _fn)
                        try:
                            img = Image.open(_candidate)
                            img.load()
                            return img.convert("RGBA")
                        except Exception:
                            continue
            except OSError:
                pass
        return None

    def _read_game_meta_and_cover(self, src: str) -> tuple[dict, Image.Image | None]:
        """Liest Metadaten und Cover konsistent aus derselben Spielequelle.

        Verhindert Mismatch-Situationen, in denen Titel und icon0 aus
        unterschiedlichen Unterordnern stammen.
        """
        if not os.path.isdir(src):
            return self._read_game_meta(src), self._load_cover_image(src)

        hint_tid = ""
        try:
            hint_src = os.path.basename(os.path.normpath(src)).upper()
            m_hint = re.search(
                r"(PPSA\d{5}|PPUS\d{5}|PPJP\d{5}|CUSA\d{5}|PUSA\d{5}|PCJS\d{5}|PCAS\d{5}|ECAS\d{5})",
                hint_src,
            )
            if m_hint:
                hint_tid = m_hint.group(1)
        except Exception:
            hint_tid = ""

        candidates = [src]
        try:
            subdirs = [
                os.path.join(src, entry)
                for entry in sorted(os.listdir(src), key=lambda v: v.lower())
                if os.path.isdir(os.path.join(src, entry))
            ]
            if hint_tid:
                subdirs.sort(
                    key=lambda p: (hint_tid not in os.path.basename(p).upper(), os.path.basename(p).lower())
                )
            candidates.extend(subdirs[:30])
        except OSError:
            pass

        # 1) Exakter Treffer: Title-ID passt zum Quellpfad-Hinweis.
        if hint_tid:
            for _cand in candidates:
                meta = self._read_game_meta(_cand, deep_scan=False)
                _tid = str(meta.get("title_id", "")).upper().strip()
                if _tid == hint_tid:
                    cover = self._load_cover_image(_cand, deep_scan=False)
                    return meta, cover

        # 2) Stabile Wahl: erst Metadaten-Kandidat bestimmen, Cover nur einmal laden.
        best_meta = None
        best_cand = None
        for _cand in candidates:
            meta = self._read_game_meta(_cand, deep_scan=False)
            _title = str(meta.get("title", "–")).strip()
            _tid = str(meta.get("title_id", "–")).strip()
            _has_title = _title not in {"", "-", "–", "Unbekannt", "�"}
            _has_tid = _tid not in {"", "-", "–", "Unbekannt", "�"}
            if _has_title or _has_tid:
                best_meta = meta
                best_cand = _cand
                # Volltreffer: sowohl Titel als auch Title-ID vorhanden.
                if _has_title and _has_tid:
                    break

        if best_cand is not None and best_meta is not None:
            cover = self._load_cover_image(best_cand, deep_scan=False)
            return best_meta, cover

        # 3) Letzter Schnellpfad: nur Cover falls keine Metadaten gefunden wurden.
        for _cand in candidates:
            cover = self._load_cover_image(_cand, deep_scan=False)
            if cover is not None:
                return self._read_game_meta(_cand, deep_scan=False), cover

        return self._read_game_meta(src), self._load_cover_image(src)

    def _load_fallback_art_image(self, src: str) -> Image.Image | None:
        """Sucht ein alternatives Bild, wenn icon0.png fehlt.

        Bevorzugt Dateien in sce_sys und Dateinamen mit typischen Cover-Begriffen.
        """
        preferred_names = (
            "icon0", "cover", "image", "pic", "background", "bg", "startup"
        )
        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        candidates: list[tuple[int, str]] = []
        try:
            seen = 0
            for root, _dirs, files in os.walk(src):
                seen += 1
                if seen > 400:
                    break
                root_low = root.replace("\\", "/").lower()
                for fn in files:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in valid_exts:
                        continue
                    name_low = os.path.splitext(fn)[0].lower()
                    score = 0
                    if "sce_sys" in root_low:
                        score += 100
                    if any(tag in name_low for tag in preferred_names):
                        score += 50
                    if fn.lower() == "icon0.png":
                        score += 1000
                    candidates.append((score, os.path.join(root, fn)))
        except OSError:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        for score, path in candidates[:25]:
            try:
                img = Image.open(path)
                img.load()
                logger.debug("Fallback-Art gefunden: %s | score=%s | size=%sx%s",
                             path, score, img.width, img.height)
                return img.convert("RGBA")
            except Exception as exc:
                logger.debug("Fallback-Art konnte nicht geladen werden: %s | %s", path, exc)
                continue
        return None

    def _meta_from_param_json_payload(self, payload: object) -> dict[str, str]:
        """Normalisiert Metadaten direkt aus einem geladenen param.json-Payload.

        **Die einzige Stelle, an der eine param.json ausgewertet wird.** Bis
        zum 03.09.2026 stand dieselbe Auswertung ein zweites Mal
        ausgeschrieben in ``_read_game_meta``; beide waren gleichwertig, aber
        eine Korrektur haette nur eine der beiden erreicht. Wer hier etwas
        aendert, aendert es fuer jeden Weg - Ordner, exFAT-Leser, virtuellen
        PFS-Leser und die Paketleser.

        Ein Aufrufer, der eine Datei liest, muss selbst pruefen, ob darin ein
        Objekt steht: Diese Methode gibt fuer alles andere gefuellte
        Platzhalter zurueck und sieht damit erfolgreich aus. In
        ``_read_game_meta`` haengt daran der Rueckfall auf die ``param.sfo``.

        Args:
            payload: Der geladene Inhalt einer ``param.json``.

        Returns:
            Die Angaben zum Spiel; nicht gefundene stehen auf dem
            Platzhalter.
        """
        meta: dict[str, str] = {
            "title": "–",
            "title_id": "–",
            "version": "–",
            "required_firmware": "–",
            "region": "–",
            "category": "–",
            "publisher": "–",
        }
        if not isinstance(payload, dict):
            return meta

        def _scalar(value: object) -> str:
            if value is None or isinstance(value, (dict, list)):
                return ""
            return str(value).strip()

        def _pick_scalar(data: dict, *keys: str) -> str:
            for key in keys:
                picked = _scalar(data.get(key))
                if picked:
                    return picked
            return "–"

        lp = payload.get("localizedParameters")
        lp_flat: dict = {}
        if isinstance(lp, dict):
            if "titleName" in lp:
                lp_flat = lp
            else:
                for lang in ("en-US", "en-GB", "en"):
                    if lang in lp and isinstance(lp[lang], dict):
                        lp_flat = lp[lang]
                        break
                if not lp_flat:
                    for value in lp.values():
                        if isinstance(value, dict):
                            lp_flat = value
                            break

        meta["title"] = (
            _scalar(lp_flat.get("titleName"))
            or _pick_scalar(payload, "titleName", "title", "name")
            or "–"
        )
        meta["title_id"] = _pick_scalar(payload, "titleId", "title_id", "contentId")
        meta["version"] = _pick_scalar(payload, "contentVersion", "masterVersion", "appVer", "version")
        meta["required_firmware"] = self._extract_required_firmware_value(payload)

        region = _pick_scalar(payload, "region", "defaultLanguage", "defaultLanguageCode")
        if region == "–":
            region = self._region_from_title_id(meta.get("title_id", ""))
        meta["region"] = region

        cat_raw = payload.get(
            "applicationCategoryType",
            payload.get("contentType", payload.get("category")),
        )
        cat_map = {0: "Spiel", 1: "DLC", 2: "Patch", 3: "App", 65536: "Spiel"}
        if isinstance(cat_raw, int):
            meta["category"] = cat_map.get(cat_raw, str(cat_raw))
        elif cat_raw is not None:
            meta["category"] = _scalar(cat_raw) or "–"

        publisher = _pick_scalar(
            payload,
            "publisher",
            "vendorName",
            "publisherName",
            "publisherLocalized",
            "developerName",
        )
        if publisher == "–":
            publisher = (
                _scalar(lp_flat.get("publisher"))
                or _scalar(lp_flat.get("vendorName"))
                or _scalar(lp_flat.get("developerName"))
                or "–"
            )
        meta["publisher"] = publisher

        # Die Content-ID steht als eigene Angabe daneben und nicht nur als
        # Rueckfall fuer die Title-ID: Sie nennt zusaetzlich Region und
        # Ausgabe ("EP0001-PPSA01234_00-..."), und der AMPR-Weg wie auch die
        # Umbenennung greifen darauf zurueck.
        content_id = _pick_scalar(payload, "contentId", "content_id")
        if content_id == "–":
            content_id = _scalar(lp_flat.get("contentId")) or "–"
        meta["content_id"] = content_id
        return meta

    def _meta_from_param_sfo_bytes(self, sfo_data: bytes) -> dict[str, str]:
        """Normalisiert Metadaten direkt aus rohen param.sfo-Bytes."""
        meta: dict[str, str] = {
            "title": "–",
            "title_id": "–",
            "version": "–",
            "required_firmware": "–",
            "region": "–",
            "category": "–",
            "publisher": "–",
        }
        sfo = self._sfo_leser(sfo_data)
        if not sfo:
            return meta

        def _sfov(key: str) -> str:
            value = sfo.get(key, "–")
            return str(value) if value else "–"

        meta["title"] = _sfov("TITLE")
        meta["title_id"] = _sfov("TITLE_ID")
        # PS4-Pakete fuehren die Content-ID unter demselben Namen wie die
        # param.json der PS5.
        meta["content_id"] = _sfov("CONTENT_ID")
        meta["version"] = _sfov("VERSION")

        firmware = "–"
        for fw_key in ("SYSTEM_VER", "SYSTEM_VERSION", "PS5_SYSTEM_VER", "TARGET_SYSTEM_VER"):
            if fw_key in sfo:
                firmware = self._normalize_required_firmware(sfo.get(fw_key))
                if firmware != "–":
                    break
        meta["required_firmware"] = firmware

        sfo_region = _sfov("REGION")
        if sfo_region == "–":
            sfo_region = self._region_from_title_id(meta["title_id"])
        meta["region"] = sfo_region
        meta["category"] = _sfov("CATEGORY")

        publisher = _sfov("PUBTOOLINFO") if _sfov("PUBTOOLINFO") != "–" else "–"
        if publisher == "–" or publisher.startswith("NP"):
            publisher = _sfov("PUBLISHER") if sfo.get("PUBLISHER") else "–"
        meta["publisher"] = publisher
        return meta

    def _extract_meta_from_exfat_reader(self, reader: Any) -> tuple[dict[str, str], Image.Image | None]:
        """Liest sce_sys-Metadaten aus einem beliebigen exFAT-Reader."""
        empty_meta: dict[str, str] = {
            "title": "–", "title_id": "–", "version": "–", "required_firmware": "–",
            "region": "–", "category": "–", "publisher": "–",
        }
        param_json_blob: bytes | None = None
        param_sfo_blob: bytes | None = None
        icon_blob: bytes | None = None
        ampr_gesehen = False
        durchlauf_vollstaendig = False

        for entry in reader.iter_files():
            rel = str(getattr(entry, "rel_path", "") or "").replace("\\", "/").lower()
            # Die AMPR-Emulation liegt in fakelib/, nicht in sce_sys/. Sie wird
            # im Vorbeigehen mitgenommen: Der Durchgang unten bricht ab, sobald
            # die drei Zieldateien da sind, und darf dafuer nicht laenger
            # laufen. Wurde er vorher abgebrochen, bleibt die Angabe leer -
            # "nicht vorhanden" waere dann eine Behauptung ueber Dateien, die
            # gar nicht angesehen wurden.
            if not ampr_gesehen and rel.endswith("fakelib/libsceampr.sprx"):
                ampr_gesehen = True
            if "sce_sys/" not in rel:
                continue
            if rel.endswith("/param.json") and param_json_blob is None:
                param_json_blob = b"".join(reader.read_file(entry))
            elif rel.endswith("/param.sfo") and param_sfo_blob is None:
                param_sfo_blob = b"".join(reader.read_file(entry))
            elif rel.endswith("/icon0.png") and icon_blob is None:
                icon_blob = b"".join(reader.read_file(entry))
            # Bei großen Titeln (viele tausend Dateien) den Baum nicht bis zum
            # Ende durchlaufen, wenn bereits alle drei Zieldateien gefunden
            # wurden – iter_files() liest sonst weiter Verzeichniscluster ein,
            # obwohl nichts Nützliches mehr folgen kann.
            #
            # Steht der AMPR-Befund noch aus, wird trotzdem abgekuerzt: Der
            # Baum eines grossen Titels dafuer ganz zu lesen waere teuer, und
            # die Angabe ist eine Nebensache gegenueber Titel und Bild. Sie
            # bleibt dann eben offen.
            if param_json_blob is not None and param_sfo_blob is not None and icon_blob is not None:
                break
        else:
            # Kein break - jede Datei des Abbilds ist durch die Schleife
            # gelaufen. Erst das erlaubt die Aussage "nicht vorhanden".
            durchlauf_vollstaendig = True

        meta = dict(empty_meta)
        if param_json_blob:
            try:
                meta = self._meta_from_param_json_payload(json.loads(param_json_blob.decode("utf-8")))
            except Exception as exc:
                logger.debug("Virtuelles exFAT-param.json konnte nicht gelesen werden: %s", exc)
        if param_sfo_blob:
            try:
                sfo_meta = self._meta_from_param_sfo_bytes(param_sfo_blob)
                for key, value in sfo_meta.items():
                    if (
                        str(meta.get(key, "")).strip() in {"", "-", "–", "Unbekannt", "�"}
                        and str(value).strip() not in {"", "-", "–", "Unbekannt", "�"}
                    ):
                        meta[key] = value
            except Exception as exc:
                logger.debug("Virtuelles exFAT-param.sfo konnte nicht gelesen werden: %s", exc)

        # Drei Zustaende, nicht zwei: gefunden, nachgesehen und nichts
        # gefunden, oder gar nicht zu Ende gesehen. Vorher gab es nur den
        # ersten - ohne Marker blieb die Angabe leer, und der Anwender
        # konnte "es ist keiner drin" nicht von "wurde nicht ermittelt"
        # unterscheiden. Beides sah gleich aus.
        if ampr_gesehen:
            meta["ampr_emu"] = self._t("info_popup.meta.ampr_emu_ja")
        elif durchlauf_vollstaendig:
            meta["ampr_emu"] = self._t("info_popup.meta.ampr_emu_nein")

        cover_img: Image.Image | None = None
        if icon_blob:
            try:
                cover_img = Image.open(io.BytesIO(icon_blob)).convert("RGBA")
                cover_img.load()
            except Exception as exc:
                logger.debug("Virtuelles exFAT-icon0 konnte nicht geladen werden: %s", exc)

        return meta, cover_img

    def _extract_meta_from_ffpfsc_virtual(self, src: str) -> tuple[dict[str, str], Image.Image | None]:
        """Versucht .ffpfsc virtuell zu lesen (exFAT oder verschachteltes PFS-in-PFS), ohne äußeren Unpack."""
        empty_meta: dict[str, str] = {
            "title": "–", "title_id": "–", "version": "–", "required_firmware": "–",
            "region": "–", "category": "–", "publisher": "–",
        }

        def _is_useful(meta: dict[str, str], cover_img: Image.Image | None) -> bool:
            return cover_img is not None or any(
                str(meta.get(key, "")).strip() not in {"", "-", "–", "Unbekannt", "�"}
                for key in ("title", "title_id", "version", "required_firmware", "category", "publisher")
            )

        try:
            if self.mkpfs_dir and self.mkpfs_dir not in sys.path:
                sys.path.insert(0, self.mkpfs_dir)
            from mkpfs.exfat import ExfatReader  # noqa: PLC0415  # type: ignore[import-not-found]
            from mkpfs.pfs import open_inner_file_view  # noqa: PLC0415  # type: ignore[import-not-found]

            inner_view_info = open_inner_file_view(Path(src))
            if inner_view_info is None:
                return empty_meta, None

            virtual_fh, backing_fh, _inner_name = inner_view_info
            try:
                try:
                    reader = ExfatReader(virtual_fh)
                    meta, cover_img = self._extract_meta_from_exfat_reader(reader)
                    if _is_useful(meta, cover_img):
                        meta["_metadata_method"] = "MkPFS PFSC + exFAT-Reader (read-only)"
                        return meta, cover_img
                except Exception as exc:
                    logger.debug("Virtueller exFAT-Read in .ffpfsc fehlgeschlagen, versuche PFS-in-PFS: %s", exc)

                try:
                    virtual_fh.seek(0)
                    pfs_reader = self._open_virtual_pfs_reader(virtual_fh)
                    if pfs_reader is not None:
                        meta, cover_img = self._extract_meta_from_exfat_reader(pfs_reader)
                        if _is_useful(meta, cover_img):
                            meta["_metadata_method"] = "MkPFS PFSC + PFS-in-PFS-Reader (read-only)"
                            return meta, cover_img
                except Exception as exc:
                    logger.debug("Virtueller PFS-in-PFS-Read in .ffpfsc fehlgeschlagen: %s", exc)
            finally:
                try:
                    # _LogicalFileView (das virtual_fh von open_inner_file_view) besitzt kein
                    # eigenes OS-Handle und implementiert daher kein close() – ein unbedingter
                    # Aufruf würde eine AttributeError im finally-Block auslösen und damit ein
                    # bereits anstehendes "return meta, cover_img" verschlucken (der schnelle
                    # Pfad würde dadurch IMMER auf den teuren Unpack-Fallback zurückfallen).
                    close_fn = getattr(virtual_fh, "close", None)
                    if callable(close_fn):
                        close_fn()
                finally:
                    backing_fh.close()
        except Exception as exc:
            logger.debug("Virtueller .ffpfsc-Read fehlgeschlagen, nutze Unpack-Fallback: %s", exc)
        return empty_meta, None

    def _extract_meta_files_from_pfs(self, pfs_path: str, out_dir: str) -> bool:
        """Liest param.json und param.sfo direkt aus einem PFS-Image via mkpfs-API.

        Entpackt **nur** die Metadaten-Dateien, nicht das gesamte Image.
        Gibt True zurück wenn mindestens eine Datei erfolgreich extrahiert wurde.

        Args:
            pfs_path: Pfad zum inneren PFS-Image (.dat).
            out_dir:  Zielverzeichnis für die extrahierten Metadaten-Dateien.
        """
        try:
            # mkpfs-Pfad sicherstellen
            if self.mkpfs_dir and self.mkpfs_dir not in sys.path:
                sys.path.insert(0, self.mkpfs_dir)

            from mkpfs.pfs import (  # noqa: PLC0415  # type: ignore[import-not-found]
                inspect_pfs_image,
                read_image_inode_payload,
                decode_inode_payload,
            )
            from pathlib import Path  # noqa: PLC0415

            targets = (
                "sce_sys/param.json",
                "sce_sys/param.sfo",
                "sce_sys/icon0.png",
            )

            # inspect_pfs_image liest Header, Inodes und baut den Dateibaum korrekt auf
            inspection = inspect_pfs_image(Path(pfs_path))
            file_inodes = inspection.file_inodes or {}
            inodes      = inspection.inodes or []

            if not file_inodes or not inodes:
                return False

            # Robust gegen unterschiedliche Separator und Groß/Kleinschreibung
            # im PFS-Dateibaum (häufige Ursache dafür, dass icon0.png nicht gefunden wird).
            norm_map: dict[str, int] = {}
            for _k, _idx in file_inodes.items():
                _nk = str(_k).replace("\\", "/").lower()
                norm_map[_nk] = _idx

            extracted_any = False
            with open(pfs_path, "rb") as fh:
                # Header nochmals parsen (fh muss offen sein für read_image_inode_payload)
                from mkpfs.pfs import parse_image_header  # noqa: PLC0415  # type: ignore[import-not-found]
                header = parse_image_header(fh)

                for rel_path in targets:
                    key_norm = rel_path.replace("\\", "/").lower()
                    inode_idx = norm_map.get(key_norm)

                    # Fallback: falls Pfad ein Präfix enthält (z.B. GAMEID/sce_sys/icon0.png)
                    if inode_idx is None:
                        suffix = "/" + os.path.basename(rel_path).lower()
                        for _nk, _idx in norm_map.items():
                            if _nk.endswith(suffix) and "sce_sys" in _nk:
                                inode_idx = _idx
                                break

                    if inode_idx is None:
                        continue

                    inode = inodes[inode_idx]
                    payload = read_image_inode_payload(fh, header, inode)
                    if inode.is_compressed:
                        try:
                            payload = decode_inode_payload(payload=payload, inode=inode)
                        except Exception as exc:
                            logger.debug("inode-Payload konnte nicht dekodiert werden: %s", exc)
                            continue
                    # Datei in out_dir schreiben
                    out_path = os.path.join(out_dir, "sce_sys", os.path.basename(rel_path))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as wf:
                        wf.write(payload)
                    extracted_any = True

            return extracted_any

        except Exception as exc:
            self._append_to_log(self._t('log.auto.0212', v0=exc))
            return False
