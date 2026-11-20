# -*- coding: utf-8 -*-
"""Das SDK der ``eboot.bin`` eines Spiels - gelesen aus einem Ordner oder einer ``.ffpkg``, ohne die Datei zu laden.

Warum das Programm das selbst liest: Die Konsole prueft beim Start das **SDK in den Programmen** (``eboot.bin``, ``.prx``/``.sprx``)
gegen ihre Firmware. Ein Backport setzt genau dieses SDK herab - die Angaben in ``sce_sys/param.json`` (``sdkVersion``,
``requiredSystemSoftwareVersion``) fasst nicht jedes Werkzeug an. Dump Forges ``inspect`` nennt nur die Angaben der ``param.json``;
das SDK der Programme (``backport_firmware``) nennt es nur, wenn das Spiel einen ``fakelib/``-Ordner hat. Wer allein nach der
``param.json`` urteilt, haelt ein schon herabgesetztes Spiel fuer eines, das noch einen Backport braucht (gemeldet 20.11.2026: ein
``.ffpkg``, das unter Firmware 12 laeuft, wurde beim Umwandeln in ein PKG als "Backport noetig" beanstandet).

Der Lesevorgang folgt Dump Forges ``sdk.rs`` (``ps5_sdk``, an den Programmen echter Spiele gegen Forges eigene Ausgabe gemessen):
Kopf der Datei (64 KiB) lesen, den Programmkopf (``PT_SCE_PROCPARAM`` oder ``PT_SCE_MODULE_PARAM``) suchen, bei einer signierten
Datei (fSELF) ueber deren Segmenttabelle auf die gespeicherte Stelle umrechnen und dort die 32 Bytes des Modulkopfs lesen. Mehr als
einige KiB werden nie gelesen, auch bei einer ``eboot.bin`` von 300 MB. Verschluesselte oder komprimierte Segmente lassen sich so
nicht lesen - das Ergebnis ist dann "nicht zu sagen", nie geraten.

Das Modul kennt keine Oberflaeche. Nichts wird veraendert.
"""
from __future__ import annotations

import os
import struct
from typing import Callable

from . import ps5_backport as _bp
from . import ufs2_leser as _ufs2

#: ``(Offset, Laenge) -> Bytes``; am Dateiende liefert sie weniger.
LeseFunktion = Callable[[int, int], bytes]

#: So viel vom Dateianfang genuegt fuer die Kopfzeilen (echte brauchen einige hundert Bytes).
KOPF = 0x10000
#: Der Modulkopf (``sceProcessParam`` / ``sceModuleParam``): so viele Bytes werden dort gelesen.
MODULKOPF = 0x20
_SDK_IM_MODULKOPF = 0xC

_ELF = b"\x7fELF"
_SELF_PS5 = b"\x54\x14\xF5\xEE"
_SELF_PS4 = b"\x4F\x15\x3D\x1D"
#: Eigenschaften eines SELF-Segments: Inhalt verschluesselt oder komprimiert - nicht an Ort und Stelle lesbar.
_SELF_VERSCHLUESSELT = 1 << 1
_SELF_KOMPRIMIERT = 1 << 3
#: Mehr Programmkoepfe hat keine echte Datei; schuetzt vor einem beschaedigten Kopf.
_MAX_PROGRAMMKOEPFE = 4096


def _zahl(daten: bytes, ab: int, fmt: str) -> "int | None":
    groesse = struct.calcsize(fmt)
    if ab < 0 or ab + groesse > len(daten):
        return None
    return struct.unpack_from(fmt, daten, ab)[0]


def sdk_wort_lesen(lesen: LeseFunktion) -> "int | None":
    """Das PS5-SDK der Datei als Zahl (``0x07000038`` = 7.00); ``None``, wenn es sich nicht lesen laesst. Wirft nie."""
    try:
        return _sdk_wort(lesen)
    except (OSError, ValueError, struct.error, OverflowError):
        return None


def _sdk_wort(lesen: LeseFunktion) -> "int | None":
    kopf = lesen(0, KOPF)
    magic = kopf[:4]
    if magic in (_SELF_PS5, _SELF_PS4):
        segmente = _zahl(kopf, 0x18, "<H")
        if segmente is None:
            return None
        elf = 0x20 + segmente * 0x20
    elif magic == _ELF:
        segmente, elf = 0, 0
    else:
        return None
    if kopf[elf:elf + 4] != _ELF:
        return None
    phoff = _zahl(kopf, elf + 0x20, "<Q")
    phentsize = _zahl(kopf, elf + 0x36, "<H")
    phnum = _zahl(kopf, elf + 0x38, "<H")
    if phoff is None or phentsize is None or phnum is None or phnum > _MAX_PROGRAMMKOEPFE:
        return None
    koepfe: "list[tuple[int, int, int]]" = []
    for i in range(phnum):
        ph = elf + phoff + i * phentsize
        art, ab, groesse = _zahl(kopf, ph, "<I"), _zahl(kopf, ph + 8, "<Q"), _zahl(kopf, ph + 0x20, "<Q")
        if art is None or ab is None or groesse is None:
            return None                       # ein unlesbarer Programmkopf: nichts davon ist zu trauen (wie Dump Forge)
        koepfe.append((art, ab, groesse))
    modul = next(((art, ab) for art, ab, _g in koepfe if art in (_bp.PT_SCE_PROCPARAM, _bp.PT_SCE_MODULE_PARAM)), None)
    if modul is None:
        return None
    art, param = modul
    stelle = param if segmente == 0 else _gespeicherte_stelle(kopf, segmente, koepfe, param)
    if stelle is None:
        return None
    modulkopf = lesen(stelle, MODULKOPF)
    erwartet = _bp.SCE_PROCESS_PARAM_MAGIC if art == _bp.PT_SCE_PROCPARAM else _bp.SCE_MODULE_PARAM_MAGIC
    for basis in (0, 8):
        if _zahl(modulkopf, basis, "<I") == erwartet:
            return _zahl(modulkopf, basis + _SDK_IM_MODULKOPF, "<I")
    return None


def _gespeicherte_stelle(kopf: bytes, segmente: int, koepfe: "list[tuple[int, int, int]]", param: int) -> "int | None":
    """Wo der Modulkopf in einer signierten Datei (fSELF) liegt: Jedes ELF-Segment hat einen Eintrag in der Segmenttabelle
    (``{Eigenschaften, Offset, gespeicherte Groesse, Speichergroesse}``, Segment-Nummer in ``Eigenschaften >> 20``); gelesen wird
    durch das erste Segment, das den Modulkopf traegt und unverschluesselt und unkomprimiert gespeichert ist."""
    for nummer, (_art, ab, groesse) in enumerate(koepfe):
        if not ab <= param < ab + groesse:
            continue
        for k in range(segmente):
            eintrag = 0x20 + k * 0x20
            eigenschaften = _zahl(kopf, eintrag, "<Q")
            gespeichert = _zahl(kopf, eintrag + 0x10, "<Q")
            if eigenschaften is None or gespeichert is None:
                continue
            if eigenschaften & (_SELF_VERSCHLUESSELT | _SELF_KOMPRIMIERT):
                continue
            if (eigenschaften >> 20) & 0xFFFF != nummer or gespeichert != groesse:
                continue
            offset = _zahl(kopf, eintrag + 8, "<Q")
            if offset is not None:
                return offset + (param - ab)
    return None


def sdk_text(wort: "int | None") -> str:
    """``0x07000038`` als ``"7.00"``, ``0x10500040`` als ``"10.50"``; ``""``, wenn es kein gueltiges SDK ist (die obersten zwei Bytes sind BCD)."""
    if not wort:
        return ""
    haupt, neben = (wort >> 24) & 0xFF, (wort >> 16) & 0xFF
    if any(b >> 4 > 9 or b & 0xF > 9 for b in (haupt, neben)):
        return ""
    return "%x.%02x" % (haupt, neben)


def _eboot_im_ordner(ordner: str) -> str:
    """Der Pfad der ``eboot.bin`` an der Wurzel des Spielordners (Gross-/Kleinschreibung egal); ``""``, wenn es keine gibt."""
    with os.scandir(ordner) as eintraege:
        for eintrag in eintraege:
            if eintrag.name.lower() == "eboot.bin" and eintrag.is_file():
                return eintrag.path
    return ""


def eboot_sdk_im_ordner(ordner: str) -> str:
    """Das SDK der ``eboot.bin`` in einem Spielordner als Text (``"10.00"``); ``""``, wenn nichts zu lesen ist."""
    try:
        pfad = _eboot_im_ordner(ordner)
        if not pfad:
            return ""
        with open(pfad, "rb") as datei:
            def lesen(ab: int, laenge: int) -> bytes:
                datei.seek(ab)
                return datei.read(laenge)
            return sdk_text(sdk_wort_lesen(lesen))
    except (OSError, ValueError):
        return ""


def eboot_sdk_in_ffpkg(abbild: str) -> str:
    """Das SDK der ``eboot.bin`` in einer ``.ffpkg`` (UFS2) als Text; ``""``, wenn nichts zu lesen ist. Entpackt nichts."""
    try:
        with _ufs2.Ufs2Leser(abbild) as leser:
            name = next((n for n, ordner, _g in leser.auflisten("") if not ordner and n.lower() == "eboot.bin"), "")
            if not name:
                return ""
            return sdk_text(sdk_wort_lesen(lambda ab, laenge: leser.datei_bereich(name, ab, laenge)))
    except (OSError, ValueError):                  # Ufs2Fehler ist ein ValueError
        return ""


def eboot_sdk(quelle: str) -> str:
    """Das SDK der ``eboot.bin`` einer Quelle: Spielordner oder ``.ffpkg``. Alles andere (``.ffpfsc``, ``.exfat``, ``.pkg``, Archive)
    kann das Programm so nicht lesen: ``""``. Wirft nie."""
    try:
        if os.path.isdir(quelle):
            return eboot_sdk_im_ordner(quelle)
        if os.path.isfile(quelle) and quelle.lower().endswith(".ffpkg"):
            return eboot_sdk_in_ffpkg(quelle)
    except (OSError, ValueError):
        pass
    return ""
