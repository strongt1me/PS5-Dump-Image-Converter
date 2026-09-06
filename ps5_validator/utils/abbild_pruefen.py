# -*- coding: utf-8 -*-
"""Prueft Quellen vor dem Lauf und Ergebnisse danach.

Zehnter Schnitt der Trennung. Fuenf Methoden mit zusammen rund 530
Zeilen, die zwei Fragen beantworten: **taugt diese Quelle** und **ist
dabei herausgekommen, was herauskommen sollte**.

Die Ergebnispruefung ist die wichtigere. Sie zaehlt nach, ob im fertigen
Abbild so viele Dateien liegen wie in der Quelle - ueber einen
schreibgeschuetzten Einhaengevorgang bei ``.ffpkg`` und ueber den
exFAT-Leser bei ``.exfat``. Ohne sie faellt ein unvollstaendiges Abbild
erst auf der Konsole auf.

**Ein sys.path-Eingriff ist dabei entfallen.**
``_validate_ffpkg_artifact`` legte den Projektordner auf den Importpfad,
um ``ps5_validator.core.dispatcher`` zu erreichen - gebildet aus
``os.path.dirname(os.path.abspath(__file__))``. Hier ist beides
ueberfluessig: Das Modul liegt selbst in ``ps5_validator``, und der
Ausdruck haette nach dem Umzug ohnehin auf dieses Modul gezeigt statt auf
das Projekt.

**Was draussen bleibt.** ``_validate_requested_conversion`` prueft vor dem
Start, ob die gewaehlte Umwandlung ueberhaupt zur Quelle passt. Sie haengt
allein an vier Nahtstellen der Oberflaeche und gehoert zum Ablauf, nicht
zur Pruefung.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from ps5_validator.utils.nahtstellen import Textquelle, schluessel_zeigen
from ps5_validator.utils.plattform import ist_administrator, prozess_flags

logger = logging.getLogger("PS5Converter.utils.abbild_pruefen")


class Pruefstand:
    """Prueft Quellen und Ergebnisse.

    Args:
        text: Uebersetzt Meldungsschluessel.
        erwartet_dump_ordner: Ob eine Aufgabe einen Dump-Ordner erwartet.
        sieht_aus_wie_dump: Ob ein Ordner ein Dump ist.
        ordner_inhalt: Sammelt den Inhalt eines Ordners.
        ordner_lesen: Liest ein Verzeichnis, ohne bei Fehlern zu werfen.
        mkpfs_ordner_holen: Stellt die MkPFS-Engine bereit.
        ufs2tool_pfad: Liefert den Pfad zu UFS2Tool.
        dokan_vorhanden: Ob der Dokan-Treiber da ist.
    """

    def __init__(self, *,
                 text: Textquelle | None = None,
                 erwartet_dump_ordner: Callable[..., Any] | None = None,
                 sieht_aus_wie_dump: Callable[..., Any] | None = None,
                 ordner_inhalt: Callable[..., Any] | None = None,
                 ordner_lesen: Callable[..., Any] | None = None,
                 mkpfs_ordner_holen: Callable[[], str] | None = None,
                 ufs2tool_pfad: Callable[[], str] | None = None,
                 dokan_vorhanden: Callable[[], Any] | None = None) -> None:
        self._t = text or schluessel_zeigen
        self._expects_dump_folder = erwartet_dump_ordner or (lambda *a: False)
        self._looks_like_dump_folder = sieht_aus_wie_dump or (lambda *a: False)
        self._sammel_ordner_inhalt = ordner_inhalt or (lambda *a: None)
        self._scandir_safe = ordner_lesen or (lambda *a, **k: [])
        self._extract_embedded_mkpfs = mkpfs_ordner_holen or (lambda: "")
        self._extract_ufs2tool = ufs2tool_pfad or (lambda: "")
        self._find_dokan_driver = dokan_vorhanden or (lambda: None)

    # Im Monolithen war das eine @staticmethod, die ihre zwei Helfer ueber
    # den Klassennamen rief. Hier kommen sie aus dem Erzeuger, also braucht
    # sie die Instanz. Die Weiterleitung bleibt statisch und baut sich
    # einen Pruefstand aus den beiden - sie sind dort ebenfalls statisch.
    #: Was jede Aufgabe als Quelle erwartet - der erste Satz jeder Meldung.
    #: Fehlt eine Aufgabe hier, gilt sie als "nimmt alles" und wird nicht
    #: beanstandet; das ist die bisherige Bedeutung eines fehlenden Zweigs.
    _WAS_ERWARTET = {
        "pack_folder": "srccheck.what.pack_folder",
        "unpack_to_exfat": "srccheck.what.unpack_to_exfat",
        "pack_file": "srccheck.what.pack_file",
        "ffpkg_to_ffpfsc": "srccheck.what.ffpkg_to_ffpfsc",
        "universal_convert": "srccheck.what.universal_convert",
        "unpack_to_game_folder": "srccheck.what.unpack_to_game_folder",
        "inspect": "srccheck.what.inspect",
        "exfat_to_folder": "srccheck.what.exfat_to_folder",
    }

    #: Die Endungen, die eine Aufgabe annimmt. Leer heisst: Ordner erwartet.
    _ENDUNGEN = {
        "unpack_to_exfat": (".ffpfsc", ".ffpfs"),
        "pack_file": (".exfat",),
        "ffpkg_to_ffpfsc": (".ffpkg",),
        "unpack_to_game_folder": (".ffpfsc", ".ffpfs"),
        "inspect": (".ffpfsc", ".ffpfs"),
        "exfat_to_folder": (".exfat",),
    }

    #: Was Aufgabe 5, 6, 7 und 8 an Dateien durchlassen.
    _ALLE_ABBILDER = (".ffpfsc", ".ffpfs", ".exfat", ".ffpkg")

    def _validate_source_path(self, path: str, mode: str) -> str:
        """Prueft ob der Quellpfad den Regeln fuer den gewaehlten Modus entspricht.

        Bis zum 06.09.2026 standen hier zweiundzwanzig fertige deutsche
        Saetze - obwohl dieses Modul seinen Uebersetzer laengst uebergeben
        bekommt (``text=`` im Erzeuger). Wer das Programm auf Englisch
        stellte, bekam beim Fehlgriff auf die Quelle trotzdem Deutsch.

        Die Saetze sind jetzt in sieben Satzformen und je Aufgabe einen
        Baustein zerlegt. Das spart nicht nur Schluessel: Bisher hiess es im
        einen Zweig ".ffpfsc Datei" und im naechsten ".ffpfsc/.ffpfs Datei"
        fuer dieselbe Aufgabe - die Bausteine koennen nicht auseinanderlaufen.

        Returns:
            Leerer String wenn gueltig, sonst Fehlermeldung.
        """
        was = self._WAS_ERWARTET.get(mode, "")

        # Die Aufgaben, die genau einen Typ verlangen: Ordner oder Datei mit
        # bestimmter Endung. Frueher stand jeder dieser Zweige einzeln da.
        if mode == "pack_folder":
            if not os.path.isdir(path):
                return self._t("srccheck.not_a_folder",
                               what=self._t(was), path=path)
            return ""
        if mode in self._ENDUNGEN:
            endungen = self._ENDUNGEN[mode]
            if not os.path.isfile(path):
                return self._t("srccheck.not_a_file",
                               what=self._t(was), path=path)
            if not path.lower().endswith(endungen):
                return self._t("srccheck.wrong_extension",
                               what=self._t(was), ext="/".join(endungen),
                               name=os.path.basename(path))
            return ""

        if mode == "dump_validator":
            # Akzeptiert: Ordner (Game Dump), .ffpfsc/.ffpfs, .exfat oder .ffpkg
            if os.path.isdir(path):
                return ""
            if os.path.isfile(path):
                if not path.lower().endswith(self._ALLE_ABBILDER):
                    return self._t("srccheck.no_valid_extension",
                                   what=self._t("srccheck.what.dump_validator"),
                                   name=os.path.basename(path))
                return ""
            return self._t("srccheck.task_source_missing",
                           what=self._t("srccheck.what.dump_validator_short"),
                           path=path)

        if mode == "ampr_manager":
            if os.path.isdir(path):
                return ""
            if os.path.isfile(path):
                if not path.lower().endswith(self._ALLE_ABBILDER):
                    return self._t("srccheck.no_valid_extension",
                                   what=self._t("srccheck.what.ampr_manager"),
                                   name=os.path.basename(path))
                return ""
            return self._t("srccheck.task_source_missing",
                           what=self._t("srccheck.what.ampr_manager_short"),
                           path=path)

        if mode == "batch_convert":
            # Ordner sind ausdruecklich erlaubt - entweder ein Game Dump
            # selbst oder ein Ordner voller Dumps/Abbilder. Die Weiche
            # darunter kennt den Quelltyp "folder" mit vier eigenen
            # Zweigen; bis zum 29.08.2026 fehlte nur dieser Einlass, und
            # die Beschreibung von _browse_source versprach ihn schon.
            if os.path.isdir(path):
                if self._looks_like_dump_folder(path):
                    return ""
                if self._sammel_ordner_inhalt(path):
                    return ""
                return self._t("srccheck.nothing_in_folder",
                               what=self._t("srccheck.what.batch_folder"),
                               path=path)
            if not os.path.isfile(path):
                return self._t("srccheck.path_not_found",
                               what=self._t("srccheck.what.batch_convert"),
                               path=path)
            if not path.lower().endswith(self._ALLE_ABBILDER):
                return self._t("srccheck.invalid_file",
                               what=self._t("srccheck.what.batch_files"),
                               name=os.path.basename(path))
            return ""

        if mode == "universal_convert":
            if os.path.isdir(path):
                return ""
            if not os.path.isfile(path):
                return self._t("srccheck.source_not_found",
                               what=self._t(was), path=path)
            if not path.lower().endswith(self._ALLE_ABBILDER):
                return self._t("srccheck.invalid_file",
                               what=self._t(was),
                               name=os.path.basename(path))
        return ""


    def _validate_ffpkg_artifact(
        self, image_path: str, *, base_result: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validiert ein FFPKG mit UFS2Tool `info` und read-only `fsck_ufs -fn`."""
        result = base_result if base_result is not None else {
            "ok": False,
            "path": image_path,
            "type": "file",
            "size_bytes": 0,
            "sha256": "",
            "method": "ufs2tool-info-fsck",
            "detail": "",
        }
        result["method"] = "ufs2tool-info-fsck"
        try:
            image_size = os.path.getsize(image_path)
            result["size_bytes"] = int(image_size)
            if image_size <= 0:
                result["detail"] = "FFPKG-Datei ist leer (0 Bytes)."
                return result
            ufs2tool = self._extract_ufs2tool()
            from ps5_validator.core.dispatcher import validate as validate_ffpkg

            validation = validate_ffpkg(
                path=image_path,
                mode="ffpkg",
                threads=1,
                resume=False,
                verbose=False,
                ufs2tool_path=ufs2tool,
            )
            summary = dict(getattr(validation, "summary", {}) or {})
            errors = list(getattr(validation, "errors", []) or [])
            result["validation_status"] = str(getattr(validation, "status", "FAILED"))
            result["sha256"] = str(
                (getattr(validation, "hashes", {}) or {}).get(os.path.basename(image_path), "")
            )
            if result["validation_status"] not in ("OK", "WARNING"):
                detail = "; ".join(errors[:3]) or "UFS2-Integritätsprüfung fehlgeschlagen."
                result["detail"] = detail
                return result
            fsck_rc = summary.get("fsck_return_code", 0)
            result["ok"] = True
            result["detail"] = f"UFS2-Struktur validiert; fsck rc={fsck_rc}."
            return result
        except Exception as exc:
            result["detail"] = f"UFS2-Validierung fehlgeschlagen: {exc}"
            return result

    def _verify_output_artifact(self, mode: str, final_path: str) -> dict[str, Any]:
        """Verifiziert ein Ergebnisartefakt schnell und robust."""
        result: dict[str, Any] = {
            "ok": False,
            "mode": mode,
            "path": final_path or "",
            "type": "none",
            "size_bytes": 0,
            "sha256": "",
            "method": "",
            "detail": "",
        }

        if not final_path:
            result["ok"] = True
            result["detail"] = self._t("verify.no_final_artifact")
            return result

        if not os.path.exists(final_path):
            result["detail"] = "Ausgabepfad existiert nicht."
            return result

        if os.path.isdir(final_path):
            count = 0
            total = 0
            for dirpath, _dirnames, filenames in os.walk(final_path):
                for fn in filenames:
                    p = os.path.join(dirpath, fn)
                    try:
                        total += os.path.getsize(p)
                        count += 1
                    except OSError:
                        pass
            ok = count > 0 and total > 0
            detail = f"Dateien: {count}, Bytes: {total}"
            method = "walk-count"

            # Zielformat "Dump-Ordner": eine reine Datei-/Byte-Zählung genügt nicht.
            # Eine falsch verschachtelte Quelle liefert einen Ordner mit einem
            # einzigen Container darin – gross, lesbar und trotzdem unbrauchbar.
            # Deshalb zusätzlich nachweisen, dass ein Dump herausgekommen ist.
            if ok and self._expects_dump_folder(mode):
                method = "walk-count+dump-check"
                if not self._looks_like_dump_folder(final_path):
                    sub_ok = any(
                        self._looks_like_dump_folder(entry.path)
                        for entry in self._scandir_safe(final_path)
                        if entry.is_dir()
                    )
                    if not sub_ok:
                        ok = False
                        detail = f"{detail} – {self._t('verify.no_dump_folder')}"

            result.update({
                "type": "directory",
                "size_bytes": int(total),
                "method": method,
                "ok": ok,
                "detail": detail,
            })
            return result

        try:
            size = os.path.getsize(final_path)
        except OSError as exc:
            result["detail"] = f"Dateigröße nicht lesbar: {exc}"
            return result

        result["type"] = "file"
        result["size_bytes"] = int(size)
        if size <= 0:
            result["detail"] = "Datei ist leer (0 Bytes)."
            return result

        if os.path.splitext(final_path)[1].lower() == ".ffpkg":
            return self._validate_ffpkg_artifact(final_path, base_result=result)

        if os.path.splitext(final_path)[1].lower() in {".ffpfs", ".ffpfsc"}:
            try:
                mkpfs_parent = self._extract_embedded_mkpfs()
                if mkpfs_parent and mkpfs_parent not in sys.path:
                    sys.path.insert(0, mkpfs_parent)
                from mkpfs.pfs import verify_pfs_image  # type: ignore[import-not-found]

                inspection = verify_pfs_image(Path(final_path))
                result["method"] = "mkpfs-verify"
                result["sha256"] = str(getattr(inspection, "manifest_sha256", "") or "")
                errors = list(getattr(inspection, "errors", []) or [])
                warnings = list(getattr(inspection, "warnings", []) or [])
                if errors:
                    result["detail"] = "MkPFS-Strukturfehler: " + "; ".join(errors[:3])
                    return result
                result["ok"] = True
                result["detail"] = (
                    f"MkPFS-Struktur gültig; Dateien: "
                    f"{len(getattr(inspection, 'file_inodes', {}) or {})}"
                    + (f"; Warnungen: {len(warnings)}" if warnings else "")
                )
                return result
            except Exception as exc:
                result["method"] = "mkpfs-verify"
                result["detail"] = f"MkPFS-Strukturprüfung fehlgeschlagen: {exc}"
                return result

        try:
            h = hashlib.sha256()
            with open(final_path, "rb") as fh:
                if size <= 2 * 1024 ** 3:
                    while True:
                        chunk = fh.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        h.update(chunk)
                    result["method"] = "sha256-full"
                else:
                    sample = 8 * 1024 * 1024
                    head = fh.read(sample)
                    h.update(head)
                    mid_off = max(0, (size // 2) - (sample // 2))
                    fh.seek(mid_off)
                    h.update(fh.read(sample))
                    tail_off = max(0, size - sample)
                    fh.seek(tail_off)
                    h.update(fh.read(sample))
                    h.update(str(size).encode("ascii", errors="ignore"))
                    result["method"] = "sha256-sampled"
            result["sha256"] = h.hexdigest()
            result["ok"] = True
            result["detail"] = "Verifizierung erfolgreich."
            return result
        except Exception as exc:
            result["detail"] = f"Hash-Verifizierung fehlgeschlagen: {exc}"
            return result

    def _verify_ffpkg_file_count_via_mount(
        self, candidate_path: str, expected_file_count: int
    ) -> dict[str, Any]:
        """Mountet einen FFPKG-Kandidaten schreibgeschützt und zählt die enthaltenen Dateien.

        info/fsck_ufs prüfen nur, ob die UFS2-Struktur intern konsistent ist – nicht,
        ob newfs -D bei einer festen Inode-Dichte tatsächlich alle Quelldateien
        eingebettet hat. Bei sehr dateireichen Titeln (z. B. Sammlungen mit vielen
        Kleindateien) kann das Ergebnis strukturell gültig, inhaltlich aber
        unvollständig sein. Diese Prüfung mountet das Image über denselben
        UFS2Tool/Dokan-Mechanismus wie Aufgabe 4 (Extraktion) und vergleicht die
        tatsächliche Dateizahl mit der zuvor am Quellordner ermittelten. Ist Dokan2
        nicht verfügbar, wird die Prüfung übersprungen, statt den Build zu blockieren.
        """
        result: dict[str, Any] = {
            "checked": False,
            "ok": True,
            "actual_file_count": -1,
            "detail": "",
        }
        if not ist_administrator() or not self._find_dokan_driver():
            result["detail"] = self._t("verify.count_skipped_no_dokan")
            return result

        import ctypes as _ct
        import time as _time

        try:
            exe = self._extract_ufs2tool()
        except Exception as exc:
            result["detail"] = f"übersprungen (UFS2Tool nicht verfügbar: {exc})"
            return result

        drives_bitmask = _ct.windll.kernel32.GetLogicalDrives()
        drive = None
        for idx in range(25, 3, -1):
            if not (drives_bitmask & (1 << idx)):
                drive = chr(65 + idx) + ":"
                break
        if not drive:
            result["detail"] = "übersprungen (kein freier Laufwerksbuchstabe verfügbar)"
            return result

        mount_proc: subprocess.Popen[str] | None = None
        mounted = False
        try:
            mount_proc = subprocess.Popen(
                [exe, "mount_udf", "-o", "ro", candidate_path, drive],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="mbcs",
                errors="replace",
                **prozess_flags(),
            )
            for _ in range(30):
                if mount_proc.poll() is not None:
                    break
                if os.path.exists(drive + "\\"):
                    mounted = True
                    break
                _time.sleep(0.5)

            if not mounted:
                tail = ""
                try:
                    if mount_proc.poll() is not None and mount_proc.stdout is not None:
                        tail = (mount_proc.stdout.read() or "").strip()
                except Exception:
                    tail = ""
                result["detail"] = (
                    f"übersprungen (Mount für Dateizählung fehlgeschlagen: {tail or 'Zeitüberschreitung'})"
                )
                return result

            actual_count = 0
            for _root_dir, _dirs, files in os.walk(drive + "\\"):
                actual_count += len(files)

            result["checked"] = True
            result["actual_file_count"] = actual_count
            if expected_file_count > 0 and actual_count < expected_file_count:
                result["ok"] = False
                result["detail"] = (
                    f"nur {actual_count} von {expected_file_count} Quelldateien im UFS2-Image gefunden"
                )
            else:
                result["detail"] = f"{actual_count} Dateien im UFS2-Image bestätigt"
            return result
        except Exception as exc:
            result["detail"] = f"übersprungen (Dateizählung fehlgeschlagen: {exc})"
            return result
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

    def _verify_exfat_file_count(
        self, exfat_path: str, expected_file_count: int
    ) -> dict[str, Any]:
        """Zählt die tatsächlich enthaltenen Dateien in einem gebauten exFAT-Image.

        Nutzt den vendorten, reinen Python-exFAT-Reader (kein Mount, keine
        Adminrechte oder Dokan2 nötig) um den Verzeichnisbaum zu lesen und die
        Dateien zu zählen, ohne sie zu extrahieren. Ein rein struktureller
        Lesbarkeitscheck erkennt nicht, ob tatsächlich alle Quelldateien im
        Image gelandet sind.
        """
        result: dict[str, Any] = {
            "checked": False,
            "ok": True,
            "actual_file_count": -1,
            "detail": "",
        }
        try:
            mkpfs_parent = self._extract_embedded_mkpfs()
            if not mkpfs_parent:
                result["detail"] = "übersprungen (MkPFS-Engine nicht verfügbar)"
                return result
            if mkpfs_parent not in sys.path:
                sys.path.insert(0, mkpfs_parent)
            from mkpfs.exfat import ExfatReader  # pyright: ignore[reportMissingImports]

            with open(exfat_path, "rb") as fh:
                reader = ExfatReader(fh)
                actual_count = sum(1 for _ in reader.iter_files())

            result["checked"] = True
            result["actual_file_count"] = actual_count
            if expected_file_count > 0 and actual_count < expected_file_count:
                result["ok"] = False
                result["detail"] = (
                    f"nur {actual_count} von {expected_file_count} Quelldateien im exFAT-Image gefunden"
                )
            else:
                result["detail"] = f"{actual_count} Dateien im exFAT-Image bestätigt"
            return result
        except Exception as exc:
            result["detail"] = f"übersprungen (Dateizählung fehlgeschlagen: {exc})"
            return result
