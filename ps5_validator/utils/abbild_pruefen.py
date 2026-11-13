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
import inspect
import logging
import os
import random
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from ps5_validator.utils import dokan_laufwerk
from ps5_validator.utils.archiv_quelle import ENDUNGEN as _ARCHIV_ENDUNGEN
from ps5_validator.utils.nahtstellen import Textquelle, schluessel_zeigen
from ps5_validator.utils.plattform import ist_administrator, prozess_flags

logger = logging.getLogger("PS5Converter.utils.abbild_pruefen")


def pfad_mit_geprueften_nutzdaten(aufruf: list[str]) -> str | None:
    """Der Ausgabepfad eines MkPFS-Aufrufs, dessen Nutzdaten MkPFS nach dem Bauen vollstaendig geprueft hat.

    Das trifft auf ``pack folder`` in der exFAT-Bauform zu (ohne ``--raw``): ``cli.py`` ruft dort nach dem Bauen
    ``run_image_check`` mit Nutzdaten auf - jeder Block der fertigen Datei wird dekodiert, bei der Stufe "schnell"
    ebenso wie bei "voll" (``--verify``). Nicht zutreffend: ``--raw`` (PFS-Bauform, bei "schnell" nur der Aufbau),
    ``--no-verify-structure`` (Stufe "aus"), ``--skip-verification`` und alle anderen Befehle.

    Args:
        aufruf: Die Argumente des Aufrufs ohne Programmnamen; der Ausgabepfad steht zuletzt.

    Returns:
        Den Ausgabepfad, sonst ``None``.
    """
    try:
        if len(aufruf) < 4 or aufruf[0] != "pack" or aufruf[1] != "folder":
            return None
        if any(a in aufruf for a in ("--raw", "--no-verify-structure", "--skip-verification")):
            return None
        pfad = str(aufruf[-1])
    except (IndexError, TypeError):
        return None
    return pfad or None


def mkpfs_aufruf_fuer_stufe(aufruf: list[str], stufe: str) -> list[str]:
    """Stellt MkPFS' eigene Dekodierung der fertigen Datei ab, wenn die Abschlusspruefung eine Stichprobe nimmt.

    Bei der Stufe "schnell" prueft das Programm das Ergebnis danach selbst (Aufbau und Stichprobe, siehe
    :func:`stichprobe_dekodieren`). MkPFS dekodiert in der exFAT-Bauform ohnehin jeden Block - gemessen am 10.11.2026
    rund 15 s bei 12,4 GB, auf einer Platte mit 50 GB ein Vielfaches -, das wuerde die Stichprobe zur Nebensache machen.
    Betroffen ist nur ``pack folder`` in der exFAT-Bauform mit Vorgabepruefung; jeder andere Aufruf und jede andere
    Stufe bleibt unveraendert.

    Args:
        aufruf: Die Argumente des Aufrufs ohne Programmnamen.
        stufe: ``"aus"``, ``"schnell"`` oder ``"voll"``.

    Returns:
        Eine Liste, in der gegebenenfalls ``--no-verify-structure`` unmittelbar hinter ``folder`` steht (die
        Positionsargumente stehen am Ende).
    """
    if stufe != "schnell" or "--verify" in aufruf or pfad_mit_geprueften_nutzdaten(aufruf) is None:
        return list(aufruf)
    neu = list(aufruf)
    neu.insert(2, "--no-verify-structure")
    return neu


#: Die Stichprobe der Abschlusspruefung ("schnell") nach dem Vorbild von ps5-dump-forge (``verify.rs``, Modus Fast):
#: zusammenhaengende Stuecke zu 128 PFSC-Bloecken (8 MiB) an zufaelligen Stellen - erstes und letztes Stueck immer -,
#: zusammen etwa 1 % der Bloecke, mindestens 4 und hoechstens 128 Stuecke (1 GiB). Zusammenhaengend, weil zufaellige
#: Einzelbloecke auf einer Platte je 64 KiB eine Kopfbewegung kosten.
_STICHPROBE_STUECK: int = 128
_STICHPROBE_ANTEIL: float = 0.01
_STICHPROBE_MIN_STUECKE: int = 4
_STICHPROBE_MAX_STUECKE: int = 128


def stichprobe_dekodieren(bild: Path, *, progress: Any = None, abbruch: Callable[[], bool] | None = None,
                          zufall: Any = None) -> dict[str, Any] | None:
    """Prueft die PFSC-Tabelle ganz und dekodiert eine Stichprobe der Bloecke eines ``.ffpfsc`` in exFAT-Bauform.

    Die Tabelle (Anfang und Laenge jedes Blocks) wird vollstaendig gelesen: Ein abgeschnittenes oder ueberschriebenes Ende
    faellt dort auf. Dekodiert werden Stuecke zu je 128 Bloecken; zlib prueft dabei seine eigene Pruefsumme, und die
    Laenge jedes Ergebnisses muss die logische Blockgroesse sein.

    Args:
        bild: Das fertige Abbild.
        progress: Ein ``mkpfs.pbar.Progress`` fuer Statuszeile und Abbruch (siehe ``_fortschritt_argument``), oder ``None``.
        abbruch: Wird zwischen den Stuecken gefragt.
        zufall: Zufallsquelle mit ``randrange`` (Tests); sonst ``random.SystemRandom``.

    Returns:
        ``None``, wenn die Stichprobe hier nicht anwendbar ist (kein Abbild mit genau einer verdichteten Datei - etwa die
        PFS-Bauform mit vielen Dateien): Dann muss jeder Block dekodiert werden. Sonst ein Dict mit ``bloecke`` (Zahl
        aller Bloecke), ``geprueft`` (Zahl der dekodierten) und ``fehler`` (Liste, hoechstens drei Eintraege).
    """
    import random

    from mkpfs.pfs import open_inner_file_view  # type: ignore[import-not-found]

    geoeffnet = open_inner_file_view(Path(bild))
    if geoeffnet is None:
        return None
    ansicht, griff, _name = geoeffnet
    try:
        if not getattr(ansicht, "_compressed", False):
            return None
        offsets = ansicht._offsets
        bloecke = len(offsets) - 1
        if bloecke <= 0:
            return None
        blockgroesse = int(ansicht._lbs)
        fehler: list[str] = []

        # 1. Die Tabelle ganz.
        for i in range(bloecke):
            laenge = offsets[i + 1] - offsets[i]
            if laenge <= 0 or laenge > blockgroesse:
                fehler.append("Block %d: unmoegliche gespeicherte Laenge %d" % (i, laenge))
                if len(fehler) >= 3:
                    break
        if not fehler:
            try:
                dateigroesse = os.path.getsize(bild)
            except OSError:
                dateigroesse = 0
            if dateigroesse and int(ansicht._base) + int(offsets[-1]) > dateigroesse:
                fehler.append("Die Block-Tabelle reicht bis %d, die Datei ist nur %d gross" % (
                    int(ansicht._base) + int(offsets[-1]), dateigroesse))
        if fehler:
            return {"bloecke": bloecke, "geprueft": 0, "fehler": fehler[:3]}

        # 2. Die Stuecke waehlen: erstes, letztes und zufaellige dazwischen.
        stuecke = -(-bloecke // _STICHPROBE_STUECK)
        gewuenscht = -(-int(bloecke * _STICHPROBE_ANTEIL) // _STICHPROBE_STUECK)
        anzahl = min(stuecke, max(_STICHPROBE_MIN_STUECKE, min(_STICHPROBE_MAX_STUECKE, gewuenscht)))
        wahl = {0, stuecke - 1}
        quelle = zufall or random.SystemRandom()
        while len(wahl) < anzahl:
            wahl.add(quelle.randrange(stuecke))

        # 3. Dekodieren.
        geprueft = 0
        for nr, stueck in enumerate(sorted(wahl)):
            if abbruch is not None and abbruch():
                raise _PruefungAbgebrochen()
            von = stueck * _STICHPROBE_STUECK
            bis = min(bloecke, von + _STICHPROBE_STUECK)
            for i in range(von, bis):
                try:
                    block = ansicht._decode_block(i)
                except Exception as exc:  # noqa: BLE001 - jeder Dekodierfehler ist ein Befund
                    fehler.append("Block %d: %s" % (i, exc))
                    break
                if len(block) != blockgroesse:
                    fehler.append("Block %d: %d statt %d Bytes nach dem Entpacken" % (i, len(block), blockgroesse))
                    break
                geprueft += 1
            if len(fehler) >= 3:
                break
            if progress is not None:
                progress.step("verify", nr + 1, len(wahl), bytes_processed=geprueft * blockgroesse)
        return {"bloecke": bloecke, "geprueft": geprueft, "fehler": fehler[:3]}
    finally:
        griff.close()


class _PruefungAbgebrochen(Exception):
    """Der Aufrufer hat die Ergebnispruefung abgebrochen.

    Wird aus dem Fortschrittshoerer der MkPFS-Pruefung geworfen. MkPFS
    faengt in ``verify_pfs_image`` nur ``OSError``/``ValueError`` - eine
    eigene Klasse kommt also bis hierher durch (am Quelltext von
    ``MkPFS-1.1.0/mkpfs/pfs.py`` belegt, Durchsicht Runde 19).
    """


EXFAT_RUECKLESEN_GANZ_BIS = 16 << 20       # bis hierher wird eine Stichprobendatei ganz verglichen
EXFAT_RUECKLESEN_ANFANG = 1 << 20          # von groesseren nur der Anfang
EXFAT_RUECKLESEN_MINDEST = 64 << 20        # so viel wird mindestens verglichen (kleine Titel ganz)
EXFAT_RUECKLESEN_MAX = 1 << 30             # und hoechstens so viel
EXFAT_RUECKLESEN_ANTEIL = 0.01             # dazwischen ein Hundertstel der Quelle
EXFAT_RUECKLESEN_PFLICHT = ("eboot.bin", "sce_sys/param.json")   # werden immer verglichen


def exfat_ruecklesen(
    leser: Any,
    quelle: str,
    *,
    ignoriert: Callable[[str], bool],
    zufall: Any = None,
    laeuft: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Liest ein gebautes exFAT mit dem eigenen Leser zurueck und vergleicht es mit der Quelle.

    Nach Dump Forge (Nutzerwahl 13.11.2026: "Ergebnis durch eigenen Leser pruefen"): Der Schreiber wird nicht an seinem
    eigenen Urteil gemessen, sondern an einem unabhaengigen Leser. Verglichen wird

    * die Dateiliste: jede Quelldatei steht im Abbild, und das Abbild kennt keine, die in der Quelle fehlt;
    * die Groesse jeder Datei;
    * der Inhalt einer Stichprobe: die Pflichtdateien (``eboot.bin``, ``sce_sys/param.json``) immer, dazu zufaellig
      gewaehlte Dateien, bis ``EXFAT_RUECKLESEN_MINDEST`` bis ``EXFAT_RUECKLESEN_MAX`` Bytes (ein Hundertstel der
      Quelle) gelesen sind. Dateien bis 16 MiB werden ganz verglichen, groessere am Anfang (1 MiB).

    Args:
        leser: Ein ``mkpfs.exfat.ExfatReader`` (oder etwas mit ``iter_files`` und ``read_file``).
        quelle: Der Spielordner, aus dem das Abbild gebaut wurde.
        ignoriert: ``mkpfs.utils.is_ignored_name`` - was der Schreiber bewusst weglaesst.
        zufall: ``random.Random`` fuer die Auswahl (Tests geben einen festen).
        laeuft: Liefert False, sobald der Lauf abgebrochen wurde.

    Returns:
        ``{"dateien", "fehlen", "zuviel", "groesse", "inhalt", "stichprobe_dateien", "stichprobe_bytes",
        "abgebrochen"}``; die vier Listen sind vollstaendig (der Aufrufer kuerzt fuer die Anzeige).
    """
    zufall = zufall or random.Random()
    erwartet: dict[str, tuple[str, int]] = {}
    for wurzel, unterordner, dateien in os.walk(quelle):
        unterordner[:] = [d for d in unterordner if not ignoriert(d)]
        for name in dateien:
            if ignoriert(name):
                continue
            voll = os.path.join(wurzel, name)
            rel = os.path.relpath(voll, quelle).replace(os.sep, "/")
            try:
                erwartet[rel] = (voll, os.stat(voll).st_size)
            except OSError:
                erwartet[rel] = (voll, -1)
    klein = {rel.lower(): rel for rel in erwartet}

    ergebnis: dict[str, Any] = {
        "dateien": 0, "fehlen": [], "zuviel": [], "groesse": [], "inhalt": [],
        "stichprobe_dateien": 0, "stichprobe_bytes": 0, "abgebrochen": False,
    }
    gefunden: set[str] = set()
    paare: list[tuple[Any, str]] = []
    for eintrag in leser.iter_files():
        ergebnis["dateien"] += 1
        rel = eintrag.rel_path if eintrag.rel_path in erwartet else klein.get(eintrag.rel_path.lower())
        if rel is None:
            ergebnis["zuviel"].append(eintrag.rel_path)
            continue
        gefunden.add(rel)
        if erwartet[rel][1] != eintrag.length:
            ergebnis["groesse"].append("%s (%d <> %d)" % (rel, eintrag.length, erwartet[rel][1]))
            continue
        paare.append((eintrag, rel))
    ergebnis["fehlen"] = sorted(rel for rel in erwartet if rel not in gefunden)

    gesamt = sum(e.length for e, _ in paare)
    budget = min(gesamt, max(EXFAT_RUECKLESEN_MINDEST,
                             min(EXFAT_RUECKLESEN_MAX, int(gesamt * EXFAT_RUECKLESEN_ANTEIL))))
    pflicht = [p for p in paare if p[1].lower() in EXFAT_RUECKLESEN_PFLICHT]
    rest = [p for p in paare if p[1].lower() not in EXFAT_RUECKLESEN_PFLICHT and p[0].length > 0]
    zufall.shuffle(rest)
    for nr, (eintrag, rel) in enumerate(pflicht + rest):
        if laeuft is not None and not laeuft():
            ergebnis["abgebrochen"] = True
            break
        if eintrag.length <= 0:
            continue
        if ergebnis["stichprobe_bytes"] >= budget and nr >= len(pflicht):
            break
        n = eintrag.length if eintrag.length <= EXFAT_RUECKLESEN_GANZ_BIS else EXFAT_RUECKLESEN_ANFANG
        if not _exfat_anfang_gleich(leser, eintrag, erwartet[rel][0], n):
            ergebnis["inhalt"].append(rel)
        ergebnis["stichprobe_dateien"] += 1
        ergebnis["stichprobe_bytes"] += n
    return ergebnis


def _exfat_anfang_gleich(leser: Any, eintrag: Any, quelle_datei: str, n: int) -> bool:
    """Vergleicht die ersten ``n`` Bytes einer Abbild-Datei mit denen der Quelldatei."""
    gelesen = bytearray()
    try:
        for stueck in leser.read_file(eintrag):
            gelesen += stueck
            if len(gelesen) >= n:
                break
    except Exception:
        return False                         # der Leser kommt an der Datei nicht durch: gilt als Abweichung
    del gelesen[n:]
    try:
        with open(quelle_datei, "rb") as fh:
            return fh.read(n) == bytes(gelesen)
    except OSError:
        return True                          # die Quelle laesst sich nicht lesen: das ist kein Fehler des Abbilds


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
        status_melden: Schreibt in die Statuszeile - hier der Fortschritt der
            Abschlusspruefung.
        validator_texte: Die uebersetzten Vorlagen der Validatoren
            (``dispatcher.MELDUNGEN``) - ihre Befunde stehen in der
            Einzelheit einer .ffpkg-Pruefung (Durchsicht, Runde 17).
        pruefstufe: Liefert die eingestellte Pruefstufe (``"aus"``, ``"schnell"``, ``"voll"``). Sie bestimmt, wie
            tief die Abschlusspruefung eines ``.ffpfs``/``.ffpfsc`` liest (siehe ``_abschluss_nur_aufbau``).
            Ohne Angabe gilt ``"voll"``.
        nutzdaten_geprueft: Sagt zu einem Pfad, ob MkPFS die Nutzdaten dieser Datei gerade beim Bauen vollstaendig
            dekodiert und geprueft hat und sie seitdem unveraendert ist. Ohne Angabe: nein.
    """

    def __init__(self, *,
                 text: Textquelle | None = None,
                 erwartet_dump_ordner: Callable[..., Any] | None = None,
                 sieht_aus_wie_dump: Callable[..., Any] | None = None,
                 ordner_inhalt: Callable[..., Any] | None = None,
                 ordner_lesen: Callable[..., Any] | None = None,
                 mkpfs_ordner_holen: Callable[[], str] | None = None,
                 ufs2tool_pfad: Callable[[], str] | None = None,
                 dokan_vorhanden: Callable[[], Any] | None = None,
                 status_melden: Callable[[str], Any] | None = None,
                 validator_texte: dict[str, str] | None = None,
                 pruefstufe: Callable[[], str] | None = None,
                 nutzdaten_geprueft: Callable[[str], bool] | None = None) -> None:
        self._t = text or schluessel_zeigen
        # Ohne Angabe gilt die gruendlichste Pruefung - so verhalten sich alle, die den Pruefstand ohne diese beiden
        # Rueckrufe bauen, wie bisher.
        self._pruefstufe = pruefstufe or (lambda: "voll")
        self._nutzdaten_geprueft = nutzdaten_geprueft or (lambda _pfad: False)
        self._validator_texte = validator_texte
        self._expects_dump_folder = erwartet_dump_ordner or (lambda *a: False)
        self._looks_like_dump_folder = sieht_aus_wie_dump or (lambda *a: False)
        self._sammel_ordner_inhalt = ordner_inhalt or (lambda *a: None)
        self._scandir_safe = ordner_lesen or (lambda *a, **k: [])
        self._extract_embedded_mkpfs = mkpfs_ordner_holen or (lambda: "")
        self._extract_ufs2tool = ufs2tool_pfad or (lambda: "")
        self._find_dokan_driver = dokan_vorhanden or (lambda: None)
        self._status_melden = status_melden or (lambda _text: None)

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

    #: Kennungen am Anfang der Abbilder: PFS-Kopf (int64 bei Offset 8), exFAT-Name
    #: im Bootsektor (Offset 3) und UFS2-Magic im Superblock bei 65536 + 1372.
    _PFS_MAGIC = 0x1332A0B
    _EXFAT_NAME = b"EXFAT   "
    _UFS2_MAGIC = 0x19540119
    _UFS2_SUPERBLOCK = 65536

    def _abbild_kennung_problem(self, path: str) -> str:
        """Kann diese Datei nach ihrer Endung ein Abbild sein? Leer, wenn ja.

        Matrixlauf vom 04.11.2026 (Aufgabe 3): Eine **leere** und eine
        **Textdatei** mit der Endung ``.exfat`` wurden "erfolgreich" in einen
        Container verpackt (Rueckgabe 0, die Abschlusspruefung nannte ihn
        "gueltig") - ``mkpfs pack file`` bettet jede Datei ein. Bei einer
        leeren oder falschen ``.ffpkg`` kam zwar ein Fehler, aber erst aus dem
        Werkzeug, und ein leerer Zielordner blieb liegen.

        Gelesen werden nur die ersten Bytes. Gemessen an 4 fremden
        ``.ffpfsc``, 20 fremden ``.exfat`` und der ``.ffpkg`` von E: sowie den
        eigenen Abbildern: alle bestehen, jede zerstoerte oder leere Probe wird
        erkannt.

        Gilt nicht fuer Aufgabe 8: Der Validator muss auch ein kaputtes Abbild
        oeffnen koennen, um es zu beanstanden.
        """
        endung = os.path.splitext(path)[1].lower()
        arten = {".exfat": "exFAT", ".ffpkg": "ffpkg", ".ffpfs": "ffpfs/ffpfsc", ".ffpfsc": "ffpfs/ffpfsc"}
        art = arten.get(endung)
        if art is None or not os.path.isfile(path):
            return ""
        name = os.path.basename(path)
        try:
            groesse = os.path.getsize(path)
            with open(path, "rb") as fh:
                kopf = fh.read(512 if endung == ".exfat" else 16)
                ufs = b""
                if endung == ".ffpkg":
                    fh.seek(self._UFS2_SUPERBLOCK)
                    ufs = fh.read(1376)
        except OSError:
            return ""                 # unlesbar: das meldet der Bau selbst
        if groesse == 0:
            return self._t("srccheck.kein_abbild_leer", name=name, art=art)
        if endung == ".exfat":
            gueltig = len(kopf) >= 11 and kopf[3:11] == self._EXFAT_NAME
            if gueltig and len(kopf) >= 0x70 and 9 <= kopf[0x6C] <= 12:
                # Eine abgebrochene Kopie behaelt ihren Anfang: Der Bootsektor nennt die Volumengroesse
                # (VolumeLength in Sektoren), die Datei ist kuerzer. Gemessen an 21 echten Abbildern:
                # die Dateigroesse ist bei allen genau diese Groesse.
                soll = struct.unpack_from("<Q", kopf, 0x48)[0] << kopf[0x6C]
                if groesse < soll:
                    return self._t("srccheck.abbild_abgeschnitten", name=name,
                                   soll=f"{soll:,}".replace(",", "."), ist=f"{groesse:,}".replace(",", "."))
        elif endung == ".ffpkg":
            gueltig = len(ufs) >= 1376 and struct.unpack_from("<I", ufs, 1372)[0] == self._UFS2_MAGIC
            if gueltig:
                # Eine abgebrochene Kopie behaelt ihren Anfang samt Superblock - aber das Dateisystem
                # sieht dann nur noch einen Teil seiner Dateien: Aufgabe 4 lieferte aus einer auf 60 %
                # gekuerzten .ffpkg EINE Datei (31 MB statt 191 Dateien) und meldete Erfolg, weil die
                # Liste der erwarteten Dateien aus demselben beschaedigten Abbild kam (Matrixlauf
                # 04.11.2026). Der Superblock nennt die Groesse: fs_size (int64 bei 1080) mal fs_fsize
                # (int32 bei 52). Gemessen an beiden echten Abbildern: die Dateigroesse ist genau das.
                fsize = struct.unpack_from("<i", ufs, 52)[0]
                anzahl = struct.unpack_from("<q", ufs, 1080)[0]
                soll = anzahl * fsize if fsize > 0 and anzahl > 0 else 0
                if soll and groesse < soll:
                    return self._t("srccheck.abbild_abgeschnitten", name=name,
                                   soll=f"{soll:,}".replace(",", "."), ist=f"{groesse:,}".replace(",", "."))
        else:
            gueltig = len(kopf) >= 16 and struct.unpack_from("<q", kopf, 8)[0] == self._PFS_MAGIC
        return "" if gueltig else self._t("srccheck.kein_abbild", name=name, art=art)

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
            return self._abbild_kennung_problem(path)

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
            # Ein Archiv (.zip, .7z, .rar) steht fuer den Spielordner darin; die Sammelkonvertierung entpackt es,
            # wenn es drankommt (``_run_flexible_conversion``). Ob ein Spiel darin liegt, zeigt sich erst dann.
            if path.lower().endswith(_ARCHIV_ENDUNGEN):
                return ""
            if not path.lower().endswith(self._ALLE_ABBILDER):
                return self._t("srccheck.invalid_file",
                               what=self._t("srccheck.what.batch_files"),
                               name=os.path.basename(path))
            return self._abbild_kennung_problem(path)

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
            return self._abbild_kennung_problem(path)
        return ""


    def _validate_ffpkg_artifact(
        self, image_path: str, *, base_result: dict[str, Any] | None = None,
        abbruch: Callable[[], bool] | None = None,
        fortschritt: Callable[[int, int], Any] | None = None,
    ) -> dict[str, Any]:
        """Validiert ein FFPKG mit UFS2Tool `info` und read-only `fsck_ufs -fn`.

        ``abbruch`` geht als ``cancel_flag`` an den Validator: Dessen
        Pruefsumme ueber die ganze Datei liess sich bis v1.9.24 nicht
        unterbrechen. Abgebrochen gilt die Abnahme als nicht bestanden
        (``ok`` False) - der Aufrufer fragt den Abbruch selbst ab.

        ``fortschritt``: ``(fertig, gesamt)`` in Bytes waehrend der Pruefsumme
        ueber die ganze Datei - bei 47 GB minutenlang; bis zum 06.10.2026 sah
        man davon nichts (Nutzer: "man hat das Gefuehl, das Programm ist
        eingefroren").
        """
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
                result["detail"] = self._t("verify.ffpkg_empty")
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
                cancel_flag=abbruch,
                texte=self._validator_texte,
                progress_cb=(None if fortschritt is None
                             else lambda fertig, gesamt, _name: fortschritt(fertig, gesamt)),
            )
            summary = dict(getattr(validation, "summary", {}) or {})
            errors = list(getattr(validation, "errors", []) or [])
            result["validation_status"] = str(getattr(validation, "status", "FAILED"))
            result["sha256"] = str(
                (getattr(validation, "hashes", {}) or {}).get(os.path.basename(image_path), "")
            )
            if result["validation_status"] not in ("OK", "WARNING"):
                detail = "; ".join(errors[:3]) or self._t("verify.ufs2_failed")
                result["detail"] = detail
                return result
            fsck_rc = summary.get("fsck_return_code", 0)
            result["ok"] = True
            result["detail"] = self._t("verify.ufs2_valid", rc=fsck_rc)
            return result
        except Exception as exc:
            result["detail"] = self._t("verify.ufs2_error", error=exc)
            return result

    #: Hoechstens so oft (Sekunden) geht ein Pruefstand in die Statuszeile.
    _FORTSCHRITT_TAKT_S = 1.0

    def _fortschritt_argument(self, pruefung: Callable[..., Any],
                              abbruch: Callable[[], bool] | None = None) -> dict[str, Any]:
        """``{"progress": ...}`` fuer die MkPFS-Pruefung - wenn sie es annimmt.

        Der Hoerer fragt zugleich ``abbruch``: MkPFS ruft ihn alle 8 MiB, und
        eine Ausnahme aus ihm beendet die Pruefung (:class:`_PruefungAbgebrochen`).
        Ohne ``progress`` - eine fremde MkPFS-Fassung - laesst sie sich nicht
        anhalten.

        Die Abschlusspruefung eines .ffpfsc dekodiert jeden Block. Bei einem
        51-GB-Titel dauert das eine Viertelstunde und mehr, und bis v1.9.19
        geschah es ohne jede Meldung: Die Statuszeile stand still, und die
        Aufhaenger-Erkennung schrieb am 12.09.2026 (Pruefmatrix J1) mitten in
        einem normalen Lauf einen Fehler samt Stapelabzug ins Protokoll. Jetzt
        steht der Prozentwert in der Statuszeile.

        ``progress`` kennt erst die eingebettete Fassung (siehe
        ``MkPFS-1.1.0/UPSTREAM.md``). Eine andere, etwa aus ``site-packages``,
        bekaeme sonst einen unbekannten Parameter - und die Pruefung schluege
        fehl, statt nur still zu laufen.

        Returns:
            ``{"progress": Progress}`` oder ``{}``.
        """
        try:
            if "progress" not in inspect.signature(pruefung).parameters:
                return {}
            from mkpfs.pbar import Progress  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fortschritt der Abschlusspruefung nicht verfuegbar: %s", exc)
            return {}
        zuletzt = [0.0, -1]

        def _hoeren(aktion, *werte):
            # Vor dem Takt: Der Abbruch soll nicht bis zur naechsten
            # Anzeige warten.
            if abbruch is not None and abbruch():
                raise _PruefungAbgebrochen()
            if aktion != "step" or len(werte) < 3:
                return
            gesamt = max(1, int(werte[2] or 1))
            prozent = min(100, int(werte[1] or 0) * 100 // gesamt)
            jetzt = time.monotonic()
            if prozent == zuletzt[1]:
                return
            if prozent < 100 and jetzt - zuletzt[0] < self._FORTSCHRITT_TAKT_S:
                return
            zuletzt[0], zuletzt[1] = jetzt, prozent
            try:
                self._status_melden(self._t("status.abschlusspruefung_fortschritt",
                                            prozent=prozent))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Statuszeile nicht beschreibbar: %s", exc)

        return {"progress": Progress(enabled=False, listener=_hoeren)}

    def _abschluss_tiefe(self, pfad: str) -> str:
        """Wie tief die Abschlusspruefung eines ``.ffpfs``/``.ffpfsc`` liest: ``"aufbau"``, ``"stichprobe"`` oder ``"voll"``.

        Bis v1.9.95 dekodierte sie **immer** jeden Block, unabhaengig von der Pruefstufe - bei der Vorgabe ("schnell")
        zusaetzlich zu MkPFS, das in der exFAT-Bauform dieselbe Datei nach dem Bauen schon vollstaendig dekodiert hatte.
        Gemessen am 10.11.2026 (12,4 GB, 20 Kerne, NVMe): Bau 63 s, MkPFS-Pruefung +15 s, diese Abschlusspruefung
        +22 s einfaedig - zusammen rund ein Viertel der Gesamtzeit; bei einem 50-GB-Titel von einer Platte eine
        Viertelstunde und mehr. Jetzt gilt, wie bei ps5-dump-forge (Modus Fast):

        * ``"aus"``: nur der Aufbau (Kopf, Inodes, Verzeichnisbaum, Tabellen).
        * ``"schnell"`` (Vorgabe): Aufbau und Stichprobe - die Block-Tabelle ganz, dazu zusammenhaengende Stuecke zu 8 MiB
          an zufaelligen Stellen (erstes und letztes immer), etwa 1 % der Bloecke, hoechstens 1 GiB
          (:func:`stichprobe_dekodieren`). Ist die Datei keine exFAT-Bauform mit einer verdichteten Datei, bleibt es bei
          jedem Block.
        * ``"voll"``: jeder Block. Hat MkPFS diese Datei beim Bauen gerade selbst vollstaendig dekodiert (exFAT-Bauform
          mit ``--verify``) und ist sie seitdem unveraendert, genuegt der Aufbau - derselbe Block wird nicht zweimal
          gelesen.
        * Jede unbekannte Angabe und ein Pruefstand ohne Rueckrufe: ``"voll"``.
        """
        try:
            stufe = str(self._pruefstufe() or "voll")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pruefstufe nicht lesbar: %s", exc)
            return "voll"
        if stufe == "aus":
            return "aufbau"
        if stufe == "schnell":
            return "stichprobe"
        try:
            return "aufbau" if self._nutzdaten_geprueft(pfad) else "voll"
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pruefmerker nicht lesbar: %s", exc)
            return "voll"

    def _als_abgebrochen(self, result: dict[str, Any]) -> dict[str, Any]:
        """Kennzeichnet eine abgebrochene Pruefung - nicht bestanden, nicht geprueft."""
        result.update({"ok": False, "abgebrochen": True,
                       "detail": self._t("verify.abgebrochen")})
        return result

    def _verify_output_artifact(self, mode: str, final_path: str,
                                abbruch: Callable[[], bool] | None = None) -> dict[str, Any]:
        """Verifiziert ein Ergebnisartefakt schnell und robust.

        ``abbruch`` wird vor und waehrend jeder langen Pruefung gefragt.
        Bis zur Durchsicht (Runde 19, U1-9) gab es ihn nicht: Nach
        "Abbrechen" lief die Abschlusspruefung trotzdem ganz - UFS2Tool
        ``info``, ``fsck`` und SHA-256 ueber eine zweistellige GB-Datei, oder
        das Dekodieren jedes Blocks einer ``.ffpfsc``. Abgebrochen traegt das
        Ergebnis ``"abgebrochen": True`` und gilt als nicht bestanden.
        """
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
            result["detail"] = self._t("verify.output_missing")
            return result

        def _abgebrochen() -> bool:
            return abbruch is not None and bool(abbruch())

        if _abgebrochen():
            return self._als_abgebrochen(result)

        if os.path.isdir(final_path):
            count = 0
            total = 0
            for dirpath, _dirnames, filenames in os.walk(final_path):
                if _abgebrochen():
                    return self._als_abgebrochen(result)
                for fn in filenames:
                    p = os.path.join(dirpath, fn)
                    try:
                        total += os.path.getsize(p)
                        count += 1
                    except OSError:
                        pass
            ok = count > 0 and total > 0
            detail = self._t("verify.folder_count", files=count, total=total)
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
            result["detail"] = self._t("verify.size_unreadable", error=exc)
            return result

        result["type"] = "file"
        result["size_bytes"] = int(size)
        if size <= 0:
            result["detail"] = self._t("verify.file_empty")
            return result

        if os.path.splitext(final_path)[1].lower() == ".ffpkg":
            result = self._validate_ffpkg_artifact(final_path, base_result=result,
                                                   abbruch=abbruch)
            # Der Validator bricht selbst ab (cancel_flag) und meldet das als
            # Fehlschlag mit seinen eigenen Worten - hier heisst es, was es ist.
            if not result.get("ok") and _abgebrochen():
                return self._als_abgebrochen(result)
            return result

        if os.path.splitext(final_path)[1].lower() in {".ffpfs", ".ffpfsc"}:
            tiefe = self._abschluss_tiefe(final_path)
            methode = {"aufbau": "mkpfs-struktur", "stichprobe": "mkpfs-stichprobe"}.get(tiefe, "mkpfs-verify")
            stichprobe: dict[str, Any] | None = None
            try:
                mkpfs_parent = self._extract_embedded_mkpfs()
                if mkpfs_parent and mkpfs_parent not in sys.path:
                    sys.path.insert(0, mkpfs_parent)
                if tiefe in ("aufbau", "stichprobe"):
                    # Kopf, Inodes, Verzeichnisbaum und Tabellen - kein Block wird dekodiert (Sekunden statt einer
                    # Viertelstunde bei einem 50-GB-Titel); bei "stichprobe" folgt eine Auswahl der Bloecke.
                    from mkpfs.pfs import inspect_pfs_image  # type: ignore[import-not-found]

                    fortschritt = self._fortschritt_argument(inspect_pfs_image, abbruch)
                    inspection = inspect_pfs_image(
                        image=Path(final_path), verify_payloads=False, **fortschritt)
                    if tiefe == "stichprobe" and not (getattr(inspection, "errors", None) or []):
                        stichprobe = stichprobe_dekodieren(
                            Path(final_path), progress=fortschritt.get("progress"), abbruch=abbruch)
                        if stichprobe is None:
                            # Keine exFAT-Bauform mit einer verdichteten Datei (etwa die PFS-Bauform mit vielen
                            # Dateien): Eine Auswahl liesse sich hier nicht zuordnen - jeder Block wie bisher.
                            from mkpfs.pfs import verify_pfs_image  # type: ignore[import-not-found]

                            methode = "mkpfs-verify"
                            inspection = verify_pfs_image(
                                Path(final_path),
                                **self._fortschritt_argument(verify_pfs_image, abbruch))
                else:
                    from mkpfs.pfs import verify_pfs_image  # type: ignore[import-not-found]

                    inspection = verify_pfs_image(
                        Path(final_path),
                        **self._fortschritt_argument(verify_pfs_image, abbruch))
                result["method"] = methode
                result["sha256"] = str(getattr(inspection, "manifest_sha256", "") or "")
                errors = list(getattr(inspection, "errors", []) or [])
                if stichprobe is not None:
                    errors += list(stichprobe.get("fehler") or [])
                warnings = list(getattr(inspection, "warnings", []) or [])
                if errors:
                    result["detail"] = self._t("verify.mkpfs_errors", errors="; ".join(errors[:3]))
                    return result
                result["ok"] = True
                dateien = len(getattr(inspection, "file_inodes", {}) or {})
                if stichprobe is not None:
                    result["detail"] = self._t("verify.mkpfs_stichprobe", anzahl=stichprobe["geprueft"],
                                               bloecke=stichprobe["bloecke"], files=dateien)
                else:
                    result["detail"] = self._t("verify.mkpfs_valid", files=dateien)
                result["detail"] += (self._t("verify.mkpfs_warnings", count=len(warnings)) if warnings else "")
                return result
            except _PruefungAbgebrochen:
                result["method"] = methode
                return self._als_abgebrochen(result)
            except Exception as exc:
                result["method"] = methode
                result["detail"] = self._t("verify.mkpfs_error", error=exc)
                return result

        try:
            h = hashlib.sha256()
            with open(final_path, "rb") as fh:
                if size <= 2 * 1024 ** 3:
                    while True:
                        if _abgebrochen():
                            return self._als_abgebrochen(result)
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
            result["detail"] = self._t("verify.hash_ok")
            return result
        except Exception as exc:
            result["detail"] = self._t("verify.hash_error", error=exc)
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
            result["detail"] = self._t("verify.count_skipped_no_ufs2tool", error=exc)
            return result

        # Alle Einhaengungen einer .ffpkg gehen nacheinander (gemeinsame Sperre, siehe dokan_laufwerk): Die Vorschau der
        # Metadaten nimmt sonst denselben Laufwerksbuchstaben.
        with dokan_laufwerk.SPERRE:
            return self._verify_ffpkg_file_count_eingehaengt(exe, candidate_path, expected_file_count, result)

    def _verify_ffpkg_file_count_eingehaengt(
        self, exe: str, candidate_path: str, expected_file_count: int, result: dict[str, Any]
    ) -> dict[str, Any]:
        """Der Teil von :meth:`_verify_ffpkg_file_count_via_mount`, der das Laufwerk hat (Sperre gehalten)."""
        drive = dokan_laufwerk.freier_buchstabe()
        if not drive:
            result["detail"] = self._t("verify.count_skipped_no_drive")
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
            mounted = dokan_laufwerk.bereit_warten(mount_proc, drive, versuche=30, pause=0.5)

            if not mounted:
                tail = ""
                try:
                    if mount_proc.poll() is not None and mount_proc.stdout is not None:
                        tail = (mount_proc.stdout.read() or "").strip()
                except Exception:
                    tail = ""
                result["detail"] = self._t("verify.count_skipped_mount",
                                           error=tail or self._t("verify.timeout"))
                return result

            actual_count = 0
            for _root_dir, _dirs, files in os.walk(drive + "\\"):
                actual_count += len(files)

            result["checked"] = True
            result["actual_file_count"] = actual_count
            if expected_file_count > 0 and actual_count < expected_file_count:
                result["ok"] = False
                result["detail"] = self._t("verify.count_ufs2_missing", found=actual_count,
                                           expected=expected_file_count)
            else:
                result["detail"] = self._t("verify.count_ufs2_ok", count=actual_count)
            return result
        except Exception as exc:
            result["detail"] = self._t("verify.count_skipped_error", error=exc)
            return result
        finally:
            if mount_proc is not None:
                dokan_laufwerk.aushaengen(drive, mount_proc)

    def _verify_exfat_inhalt(
        self, exfat_path: str, src_dir: str, laeuft: Callable[[], bool] | None = None
    ) -> dict[str, Any]:
        """Liest das fertige exFAT mit dem eigenen Leser zurueck und vergleicht es mit der Quelle.

        Siehe ``exfat_ruecklesen``. ``ok`` ist False bei fehlenden oder zusaetzlichen Dateien, abweichender Groesse
        oder abweichendem Inhalt der Stichprobe; ``lesefehler`` bei einem Abbild, das der Leser nicht oeffnet.
        """
        result: dict[str, Any] = {"checked": False, "ok": True, "detail": ""}
        try:
            mkpfs_parent = self._extract_embedded_mkpfs()
            if not mkpfs_parent:
                result["detail"] = self._t("verify.count_skipped_no_mkpfs")
                return result
            if mkpfs_parent not in sys.path:
                sys.path.insert(0, mkpfs_parent)
            from mkpfs.exfat import ExfatReader  # pyright: ignore[reportMissingImports]
            from mkpfs.utils import is_ignored_name  # pyright: ignore[reportMissingImports]

            try:
                with open(exfat_path, "rb") as fh:
                    befund = exfat_ruecklesen(ExfatReader(fh), src_dir, ignoriert=is_ignored_name, laeuft=laeuft)
            except Exception as exc:
                result["lesefehler"] = True
                result["detail"] = self._t("verify.count_skipped_error", error=exc)
                return result
        except Exception as exc:
            result["detail"] = self._t("verify.count_skipped_error", error=exc)
            return result

        result["checked"] = not befund["abgebrochen"]
        result["befund"] = befund
        kurz = lambda liste: ", ".join(liste[:3]) + (" ..." if len(liste) > 3 else "")   # noqa: E731
        fehler: list[str] = []
        if befund["fehlen"]:
            fehler.append(self._t("verify.inhalt_fehlen", n=len(befund["fehlen"]), beispiele=kurz(befund["fehlen"])))
        if befund["zuviel"]:
            fehler.append(self._t("verify.inhalt_zuviel", n=len(befund["zuviel"]), beispiele=kurz(befund["zuviel"])))
        if befund["groesse"]:
            fehler.append(self._t("verify.inhalt_groesse", n=len(befund["groesse"]), beispiele=kurz(befund["groesse"])))
        if befund["inhalt"]:
            fehler.append(self._t("verify.inhalt_inhalt", n=len(befund["inhalt"]), beispiele=kurz(befund["inhalt"])))
        if fehler:
            result["ok"] = False
            result["detail"] = "; ".join(fehler)
        else:
            result["detail"] = self._t("verify.inhalt_ok", dateien=befund["dateien"],
                                       stichprobe=befund["stichprobe_dateien"],
                                       mb=befund["stichprobe_bytes"] // (1 << 20))
        return result

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
                result["detail"] = self._t("verify.count_skipped_no_mkpfs")
                return result
            if mkpfs_parent not in sys.path:
                sys.path.insert(0, mkpfs_parent)
            from mkpfs.exfat import ExfatReader  # pyright: ignore[reportMissingImports]

            try:
                with open(exfat_path, "rb") as fh:
                    reader = ExfatReader(fh)
                    actual_count = sum(1 for _ in reader.iter_files())
            except Exception as exc:
                # Das Abbild selbst laesst sich nicht lesen. Fuer fremde Abbilder bleibt das "uebersprungen" (der
                # Leser kennt nicht jede Abart); wer ein Abbild eben selbst gebaut hat, wertet ``lesefehler`` als
                # Fehler: Ein Schreiber, dessen Ergebnis der eigene Leser nicht oeffnet, hat etwas Defektes gebaut
                # (Gesamtpruefung 11.11.2026, S3). Vorher galt auch das als bestanden.
                result["lesefehler"] = True
                result["detail"] = self._t("verify.count_skipped_error", error=exc)
                return result

            result["checked"] = True
            result["actual_file_count"] = actual_count
            if expected_file_count > 0 and actual_count < expected_file_count:
                result["ok"] = False
                result["detail"] = self._t("verify.count_exfat_missing", found=actual_count,
                                           expected=expected_file_count)
            else:
                result["detail"] = self._t("verify.count_exfat_ok", count=actual_count)
            return result
        except Exception as exc:
            result["detail"] = self._t("verify.count_skipped_error", error=exc)
            return result
