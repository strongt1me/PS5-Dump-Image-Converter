# -*- coding: utf-8 -*-
"""Die Huelle um die Befehlszeile von **Dump Forge** (``ps5-dump-forge``) - der dritte, waehlbare Paketersteller.

Auftrag (Nutzer, 16.11.2026): ``.ffpkg``, ``.ffpfsc``, ``.ffpfs``, ``.exfat`` und Dump-Ordner sollen im Bereich
"PKG / FPKG" in ein PKG (FPKG) umgewandelt werden - "1:1 so wie bei der aktuellsten Version von Dump Forge". Dieses
Modul ruft darum Forge selbst auf, statt seinen Weg nachzubauen: ``ps5-dump-forge convert <Quelle> --to pkg`` liest
die Quelle ueber seinen Lesebaum (ohne Zwischenordner, auch das Abbild in einer ``.ffpfsc``), baut das Debug-Paket,
liest es zurueck und prueft es.

Dump Forge (quer3q, GPL-3.0-or-later) liegt als fertige Befehlszeile je Plattform unter
``Dump-Forge-CLI/<Plattform>/`` (Windows x64, Linux x64 statisch, macOS universal; Quelle, Fassung und Pruefsummen in
``Dump-Forge-CLI/README.md``). Forge schreibt den Fortschritt als **eine JSON-Zeile je Ereignis** auf stdout
(``{"kind": "stages"|"progress"|"log"|"done", ...}``) und eine Kurzfassung fuer Menschen auf stderr; beides kommt hier
ueber :func:`ps5_validator.utils.ps5_pkg_werkzeug.laufen` an (gleiche Abbruch-, Fenster- und Aufraeumregeln wie bei
den anderen Werkzeugen).

Das Modul kennt keine Oberflaeche und keine Sprachtexte: Der Fortschritt geht als ``(Prozent, Stufe)`` an das Fenster,
das die Stufe uebersetzt; Protokollzeilen Forges bleiben in Forges Englisch (so steht dasselbe im Forge-Fenster).
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import platform
import re
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from . import ps5_pkg_werkzeug as wz
#: Die Abbildformate, die Forge als Quelle liest, nach Endung (klein) - der Wert ist Forges eigener Formatname.
from .pkg_plattform import ENDUNGEN_ABBILD

#: Ordner im Projekt (und im Bau), darin je Plattform ein Unterordner.
ORDNER = "Dump-Forge-CLI"

#: Forges Kompressionsstufen fuer ``--to pkg`` (``--kraken``), die erste ist die Vorgabe von Forge.
KRAKEN_STUFEN = ("fast", "balanced", "smallest", "stored")

#: Der Teil der Werkzeugausgabe, der ein Ereignis ist (die menschenlesbare Fassung beginnt nie so).
_EREIGNIS_ANFANG = '{"kind"'

#: Von diesen Protokollzeilen Forges kommen bei grossen Spielen hunderte gleichartige - es werden so viele gezeigt,
#: der Rest wird gezaehlt und am Ende als eine Zeile gemeldet (gemessen an einem Spiel mit 72 Dateien: 14 + 13 Zeilen).
_GRUPPEN = ("fpkg: leaving out ", "fpkg: repairing ")
_GRUPPE_ZEIGEN = 5

_Zeile = Callable[[str], None]
_Abbruch = Callable[[], bool]


def unterordner() -> str:
    """Die Plattform dieses Rechners, wie die Ordner unter ``Dump-Forge-CLI`` heissen; ``""``, wenn es keine gibt.

    Windows = ``win-x64``, mit einem arm64-Python ``win-arm64`` (ein x64-Python meldet auch auf einem ARM-Rechner ``AMD64``);
    macOS (Apple Silicon und Intel gleichermassen) = ``macos-universal``; Linux auf x86-64 = ``linux-x64`` (statisch gegen
    musl gebunden), auf arm64 = ``linux-arm64`` (dynamisch gegen glibc gebunden).
    """
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if sys.platform == "win32":
        return "win-arm64" if arm else "win-x64"
    if sys.platform == "darwin":
        return "macos-universal"
    if platform.machine().lower() in ("x86_64", "amd64"):
        return "linux-x64"
    return "linux-arm64" if arm else ""


def dateiname() -> str:
    return "ps5-dump-forge.exe" if sys.platform == "win32" else "ps5-dump-forge"


def werkzeug_suchen(wurzeln: "list[str] | None" = None) -> str:
    """Pfad zur Befehlszeile (``.exe`` unter Windows), sonst ``""`` - derselbe Suchweg wie bei ``ffpfsc-pkg-tool``."""
    unter = unterordner()
    if not unter:
        return ""
    # Windows arm64 fuehrt auch die x64-Fassung aus (Emulation): fehlt die native, nimmt die Suche diese.
    for ordner in (unter, "win-x64") if unter == "win-arm64" else (unter,):
        for wurzel in wurzeln or []:
            kandidat = os.path.join(wurzel, ORDNER, ordner, dateiname())
            if os.path.isfile(kandidat):
                return kandidat
    return ""


#: So viele Bytes darf der Name einer Ausgabe ohne Endung haben, sonst haengt ShadowMount+ sie nicht ein und Forge
#: lehnt den Namen ab (``preflight::stem_limit``; auch fuer ``.pkg``).
STAMM_GRENZE = 63


def dateiname_fuer(titel: str, kennung: str = "") -> str:
    """``Titel [PPSA00000].pkg`` - der Titel wird gekuerzt, damit der Name ohne Endung in 63 Bytes (UTF-8) passt.

    Die Kennung in eckigen Klammern bleibt immer ganz stehen; gekuerzt wird nur der Titel (an einer Zeichengrenze,
    ohne Leerzeichen und Punkte am Ende). Ohne Titel bleibt die Kennung allein, ohne beides ``Paket``.
    """
    titel = str(titel or "").strip()
    anhang = (" [%s]" % kennung) if kennung and titel else ("[%s]" % kennung if kennung else "")
    platz = max(0, STAMM_GRENZE - len(anhang.encode("utf-8")))
    kurz = titel.encode("utf-8")[:platz].decode("utf-8", errors="ignore").rstrip(" .")
    stamm = (kurz + anhang) if (kurz or anhang) else "Paket"
    return stamm + ".pkg"


def stamm_kuerzen(dateiname: str, grenze: int = STAMM_GRENZE) -> str:
    """Kuerzt den Namen ohne Endung auf ``grenze`` Bytes (UTF-8, an einer Zeichengrenze, ohne Leerzeichen und Punkte am Ende)."""
    stamm, endung = os.path.splitext(str(dateiname))
    kurz = stamm.encode("utf-8")[:max(1, int(grenze))].decode("utf-8", errors="ignore").rstrip(" .")
    return (kurz or "Spiel") + endung


def ist_paket(pfad: str) -> bool:
    """Ein ``.pkg`` (Datei): Forge liest es im Strom (``inspect``, ``convert``), ohne etwas zu entpacken."""
    return os.path.splitext(str(pfad))[1].lower() == ".pkg" and os.path.isfile(str(pfad))


def abbild_art(pfad: str) -> str:
    """Forges Formatname (``ffpkg``, ``ffpfsc``, ``ffpfs``, ``exfat``) einer Abbilddatei nach der Endung, sonst ``""``."""
    return ENDUNGEN_ABBILD.get(os.path.splitext(str(pfad))[1].lower(), "")


def ist_abbild(pfad: str) -> bool:
    return bool(abbild_art(pfad)) and os.path.isfile(pfad)


# ---------------------------------------------------------------------------------------------------------------- lesen
def _cover_schreiben(daten_url: str, ordner: str) -> str:
    """Schreibt Forges Cover (``data:image/png;base64,...``) als ``icon0.png`` in ``ordner``; ``""``, wenn keins brauchbar."""
    if not isinstance(daten_url, str) or not daten_url.startswith("data:image/png;base64,"):
        return ""
    try:
        png = base64.b64decode(daten_url.split(",", 1)[1], validate=False)
    except (binascii.Error, ValueError):
        return ""
    if not png.startswith(b"\x89PNG"):
        return ""
    pfad = os.path.join(ordner, "icon0.png")
    try:
        with open(pfad, "wb") as f:
            f.write(png)
    except OSError:
        return ""
    return pfad


def inspect_daten(werkzeug: str, pfad: str, *, abbruch: "_Abbruch | None" = None, popen_extra: "dict | None" = None,
                  vorspann: "tuple[str, ...]" = ()) -> dict:
    """``inspect <Quelle> --json``: Forges Beschreibung eines Abbilds oder Spielordners als Woerterbuch.

    Raises:
        wz.Fehler: die Befehlszeile laesst sich nicht starten, liest die Quelle nicht oder antwortet nicht mit JSON.
    """
    rc, aus = wz.laufen(werkzeug, [*vorspann, "inspect", pfad, "--json"], abbruch=abbruch, popen_extra=popen_extra)
    if rc == -1:
        raise wz.Fehler("abgebrochen")
    if rc != 0:
        raise wz.Fehler(_fehlertext(aus))
    return wz._json_aus(aus)  # noqa: SLF001 - dieselbe Aufbereitung wie bei ffpfsc-pkg-tool


def braucht_ampr(daten: dict) -> "bool | None":
    """Braucht das Spiel AMPR EMU - und bringt keinen mit? Nach Forges ``inspect``-Antwort.

    ``True``: Die ``eboot.bin`` importiert ``libSceAmpr`` (``lz4.imports_ampr``), und weder eine Laufzeit
    (``lz4.runtime``) noch ein Emulator namens AMPR liegt im Spiel. ``False``: kein Import oder ein Emulator ist da.
    ``None``: Die Antwort sagt dazu nichts (kein Schluessel ``lz4`` - eine aeltere Befehlszeile), dann nichts raten.

    Gemessen (16.11.2026) an Arcade Game Zone: ohne Einbau ``imports_ampr`` wahr, ``runtime`` "none", ``emulators``
    leer; mit AMPR EMU ``runtime`` "other" und ``emulators`` mit ``fakelib/libSceAmpr.sprx`` (Name "AMPR"). Ein Spiel
    ohne Import (Jobee's Lair) hat ``lz4`` gleich ``null``.
    """
    if not isinstance(daten, dict) or "lz4" not in daten:
        return None
    lz4 = daten.get("lz4")
    if not isinstance(lz4, dict) or lz4.get("imports_ampr") is not True:
        return False
    if str(lz4.get("runtime") or "none").strip().lower() != "none":
        return False
    for emulator in daten.get("emulators") or []:
        if not isinstance(emulator, dict):
            continue
        if (str(emulator.get("name", "")).strip().lower() == "ampr"
                or str(emulator.get("path", "")).strip().lower().endswith("libsceampr.sprx")):
            return False
    return True


def ampr_bedarf(werkzeug: str, pfad: str, *, abbruch: "_Abbruch | None" = None, popen_extra: "dict | None" = None,
                vorspann: "tuple[str, ...]" = ()) -> "bool | None":
    """Liest die Quelle mit ``inspect`` und sagt, ob AMPR EMU fehlt (:func:`braucht_ampr`); ``None``, wenn nicht lesbar.

    Kein Fehler dringt nach aussen: Es ist eine Hilfe vor dem Lauf, kein Hindernis (auch ein Abbruch ergibt ``None``).
    """
    try:
        return braucht_ampr(inspect_daten(werkzeug, pfad, abbruch=abbruch, popen_extra=popen_extra, vorspann=vorspann))
    except wz.Fehler:
        return None


#: Dateien, mit denen ein Titel PlayGo-Inhalte erklaert (wie ``PS5ConverterGUI._PLAYGO_MERKMALE``; ein Test haelt beide gleich).
PLAYGO_MERKMALE = ("sce_sys/playgo-scenario.json", "sce_sys/playgo-chunk.dat", "sce_sys/playgo_chunk.dat")


@dataclass
class QuellFakten:
    """Was Forges ``inspect`` ueber eine Quelle sagt, soweit die Rueckfragen des Programms es brauchen.

    Eine Antwort von Forge versorgt AMPR EMU (inklusive der NG-Packs), DLC EMU und PlayGo gemeinsam - auch fuer ein
    ``.ffpkg``, das die eigene Dateiliste des Programms nicht lesen kann.
    """

    #: Die ``eboot.bin`` laedt ``libSceAmpr``.
    ampr_importiert: bool = False
    #: ``True``: AMPR EMU wird gebraucht und liegt nicht im Spiel (:func:`braucht_ampr`); ``None``: nicht zu sagen.
    ampr_fehlt: "bool | None" = None
    #: ``""`` (ungepackt), ``"lz4"`` (``ampr_assets``-Packs) oder ``"zstd"`` (``ampr_zstd``-Packs).
    gepackt: str = ""
    #: Forges Name der Laufzeit in ``fakelib/libSceAmpr.sprx``: ``none``, ``other``, ``zstd`` (ampr-emu-ng) usw.
    laufzeit: str = ""
    #: Die Emulatoren in ``fakelib/`` (Namen klein): ``ampr``, ``dlc``, ``playgo``, ``other``.
    emulatoren: tuple = ()
    #: Das Spiel traegt Zusatzinhalte (Forges ``dlcs``) ...
    dlc_vorhanden: bool = False
    #: ... und DLC EMU meldet sie schon (Emulator DLC oder ein Eintrag in ``dlc_emu.ini``).
    dlc_emuliert: bool = False
    #: Woran Forge das erste DLC erkannt hat (sein Ordner, sonst die Content-ID) - fuer die Rueckfrage.
    dlc_merkmal: str = ""
    #: Das erste PlayGo-Merkmal unter den Dateien (``sce_sys/playgo-scenario.json`` usw.), sonst ``""``.
    playgo_merkmal: str = ""
    #: Die SDK-Fassung der ``eboot.bin`` und die Firmware, die ``param.json`` verlangt (Forge: ``"7.00"``, ``"9.60"``).
    sdk: str = ""
    firmware: str = ""
    #: Das Spiel traegt schon einen Backport: Ersatzbibliotheken in ``fakelib/`` (Forge: ``backport``). Nicht ``backport_firmware``: Forge
    #: setzt es, sobald irgendeine Datei in ``fakelib/`` liegt, auch bei einem Spiel nur mit AMPR EMU, PlayGo oder DLC EMU dort
    #: (gemessen 18.11.2026: ``backport`` leer, ``backport_firmware`` "2.00"; Forges eigene Ausgabe wertet nur ``backport``).
    backport_vorhanden: bool = False

    @property
    def verlangt_teile(self) -> "tuple[int, int] | None":
        """Das Meiste, was das Spiel verlangt, als (Haupt-, Nebenversion): SDK der ``eboot.bin`` oder verlangte Firmware."""
        teile = [t for t in (_teile(self.sdk), _teile(self.firmware)) if t and t[0] > 0]
        return max(teile) if teile else None

    @property
    def verlangt_haupt(self) -> int:
        """Die Hauptversion dazu (0 = unbekannt)."""
        teile = self.verlangt_teile
        return teile[0] if teile else 0

    @property
    def verlangt_text(self) -> str:
        """Die Angabe dazu in Forges Schreibweise (``"10.00"``); ``""``, wenn nichts bekannt ist."""
        teile = self.verlangt_teile
        return "%d.%02d" % teile if teile else ""

    def backport_noetig(self, konsole: str) -> bool:
        """Verlangt das Spiel mehr, als die Konsole hat - und ist es noch nicht herabgesetzt?

        BACKPORT setzt das SDK der ``eboot.bin`` und die verlangte Firmware der ``param.json`` herab
        (``ps5_backport``): Beides zaehlt hier, verglichen wie in der Bibliothek (Haupt- und Nebenversion,
        ``bibliothek.firmware_vergleichen``). ``konsole`` ist ihre Firmware als Text (``"12.00"``); ``"7.99"`` steht fuer
        "irgendeine 7.xx" (nur die Hauptversion bekannt), ``""`` fuer unbekannt - dann ist nichts noetig.
        """
        ist = _teile(konsole)
        verlangt = self.verlangt_teile
        return bool(not self.backport_vorhanden and ist and ist[0] > 0 and verlangt and verlangt > ist)

    @property
    def dlc_fehlt(self) -> bool:
        """Zusatzinhalte im Spiel, aber nichts meldet sie an der Konsole."""
        return self.dlc_vorhanden and not self.dlc_emuliert

    @property
    def playgo_fehlt(self) -> bool:
        """Das Spiel erklaert PlayGo-Inhalte, und der PlayGo-Stub liegt nicht darin."""
        return bool(self.playgo_merkmal) and "playgo" not in self.emulatoren


def _teile(text) -> "tuple[int, int] | None":
    """Haupt- und Nebenversion einer Angabe wie ``"10.00"`` oder ``"9.60"``; ``None``, wenn es keine ist."""
    treffer = re.match(r"\s*(\d{1,2})\.(\d{1,2})", str(text or ""))
    return (int(treffer.group(1)), int(treffer.group(2))) if treffer else None


def _playgo_merkmal_in(pfade) -> str:
    gesehen = {str(p or "").replace("\\", "/").lower().lstrip("/") for p in pfade}
    for merkmal in PLAYGO_MERKMALE:
        if merkmal in gesehen or any(p.endswith("/" + merkmal) for p in gesehen):
            return merkmal
    return ""


def quellfakten(daten: dict) -> QuellFakten:
    """Die Fakten aus Forges ``inspect``-Antwort (rein, ohne Start)."""
    if not isinstance(daten, dict):
        return QuellFakten()
    lz4 = daten.get("lz4") if isinstance(daten.get("lz4"), dict) else {}
    gepackt = "lz4" if lz4.get("packed") is not None else ("zstd" if daten.get("zstd_packed") is True else "")
    emulatoren = tuple(sorted({str(e.get("name", "")).strip().lower()
                               for e in (daten.get("emulators") or []) if isinstance(e, dict) and e.get("name")}))
    dlcs = [d for d in (daten.get("dlcs") or []) if isinstance(d, dict)]
    dateien = daten.get("files") if isinstance(daten.get("files"), list) else []
    pfade = [str(f.get("path", "")) for f in dateien if isinstance(f, dict)]
    return QuellFakten(
        ampr_importiert=lz4.get("imports_ampr") is True,
        ampr_fehlt=braucht_ampr(daten),
        gepackt=gepackt,
        laufzeit=str(lz4.get("runtime") or ""),
        emulatoren=emulatoren,
        dlc_vorhanden=bool(dlcs),
        dlc_emuliert="dlc" in emulatoren or any(d.get("emulated") for d in dlcs),
        dlc_merkmal=str((dlcs[0].get("folder") or dlcs[0].get("content_id") or "") if dlcs else ""),
        playgo_merkmal=_playgo_merkmal_in(pfade),
        sdk=str(daten.get("sdk") or ""),
        firmware=str(daten.get("firmware") or ""),
        backport_vorhanden=bool(daten.get("backport")),
    )


def quellfakten_lesen(werkzeug: str, pfad: str, *, abbruch: "_Abbruch | None" = None, popen_extra: "dict | None" = None,
                      vorspann: "tuple[str, ...]" = ()) -> "QuellFakten | None":
    """Liest die Quelle mit ``inspect`` und gibt ihre :class:`QuellFakten`; ``None``, wenn Forge sie nicht lesen konnte.

    Kein Fehler dringt nach aussen: Es ist eine Hilfe vor dem Lauf, kein Hindernis (auch ein Abbruch ergibt ``None``).
    """
    try:
        return quellfakten(inspect_daten(werkzeug, pfad, abbruch=abbruch, popen_extra=popen_extra, vorspann=vorspann))
    except wz.Fehler:
        return None


#: Die Wurzeldateien, an denen ein Spielordner als gepackt zu erkennen ist: der Index der zstd-Packs (ampr-emu-ng) und das Manifest der
#: LZ4-Packs (``ampr_assets``-Bestand des Packwerkzeugs). Ein Test haelt beide Namen gleich denen der Packmodule.
PACK_INDEXE = (("ampr_zstd.index", "zstd"), ("ampr_assets.index", "lz4"))


def gepackt_im_ordner(ordner: str) -> str:
    """``"zstd"`` oder ``"lz4"``, wenn im Spielordner ein Pack-Index liegt, sonst ``""`` - ohne Forge, nur nach den Dateien an der Wurzel.

    Die zweite Meinung zu Forges ``inspect`` (:attr:`QuellFakten.gepackt`): Ein Manifest, das Forge nicht lesen kann (beschaedigt, fremde
    Fassung), meldet es nicht als gepackt - die Pack-Baender liegen aber trotzdem im Spiel.
    """
    try:
        for name, verfahren in PACK_INDEXE:
            if os.path.isfile(os.path.join(ordner, name)):
                return verfahren
    except (OSError, TypeError, ValueError):
        pass
    return ""


def lesen(werkzeug: str, pfad: str, arbeitsordner: "str | None" = None, *, abbruch: "_Abbruch | None" = None,
          popen_extra: "dict | None" = None, vorspann: "tuple[str, ...]" = ()) -> "wz.PaketInfo":
    """Liest ein Abbild (oder einen Spielordner) fuer die Anzeige: ``inspect --json`` und das Cover.

    Forge liest dazu nur, was es braucht (``param.json``, Cover, Dateiliste) - ein ``.exfat`` oder ``.ffpfsc`` wird
    nicht entpackt. ``vorspann`` steht nur fuer Tests (ein Skript statt der echten Befehlszeile).

    Raises:
        wz.Fehler: die Befehlszeile laesst sich nicht starten, liest die Quelle nicht oder antwortet nicht mit JSON.
    """
    daten = inspect_daten(werkzeug, pfad, abbruch=abbruch, popen_extra=popen_extra, vorspann=vorspann)
    param = daten.get("param_json")
    param = param if isinstance(param, dict) else {}
    art = str(daten.get("kind", "") or "")
    info = wz.PaketInfo(
        pfad=pfad,
        groesse=os.path.getsize(pfad) if os.path.isfile(pfad) else int(daten.get("total_bytes", 0) or 0),
        typ=wz.TYP_ORDNER if art == "folder" else wz.TYP_ABBILD,
        content_id=str(daten.get("content_id", "") or ""),
        title_id=str(daten.get("title_id", "") or ""),
        titel=str(daten.get("title_name", "") or "") or wz.titel_aus_param(param),
        param=param,
        abbild=art,
        befunde=[str(z) for z in (daten.get("findings") or [])],
        zusatzinhalt=bool(daten.get("additional_content")),
        patch=bool(daten.get("patch")),
        fakten=quellfakten(daten),
    )
    try:
        ordner = tempfile.mkdtemp(prefix="ps5conv_pkgcover_", dir=arbeitsordner or None)
    except OSError:
        return info
    info.arbeit = ordner
    info.icon = _cover_schreiben(daten.get("cover"), ordner)
    return info


# ---------------------------------------------------------------------------------------------------------------- bauen
@dataclass
class ForgeBau:
    """Was ein Bau ergab (aus Forges ``done``-Ereignis)."""

    pfad: str
    bytes: int = 0
    dateien: int = 0
    #: Forges Pruefzeilen ("fpkg verify: ...", "check: ..."), je Zeile eine bestandene Pruefung.
    pruefungen: list = field(default_factory=list)
    #: ``fast`` (Stichprobe, Vorgabe) oder ``full`` (jedes Byte).
    modus: str = "fast"
    geprueft_bytes: int = 0
    gesamt_bytes: int = 0
    proben: int = 0


#: Die Abbildformate, in die ``convert`` ein Paket (oder einen Ordner) im Strom schreibt - ohne Zwischenordner.
ABBILD_ZIELE = ("ffpkg", "ffpfsc", "ffpfs", "exfat")

#: So viele Bytes darf der Name einer ``.ffpfsc`` ohne Endung haben (Forge: ``preflight::stem_limit``, 58 statt 63).
STAMM_GRENZE_FFPFSC = 58


#: Die Packverfahren, die Forge beim Umwandeln entpacken kann (``--lz4-unpack``, ``--zstd-unpack``); ``""`` = nicht entpacken.
ENTPACK_VERFAHREN = ("lz4", "zstd")


def convert_argumente(quelle: str, ziel: str, *, kraken: str = "fast", voll_pruefen: bool = False,
                      backport_entfernen: bool = False, kerne: int = 0, format: str = "pkg",
                      stufe: "int | None" = None, entpacken: str = "") -> "list[str]":
    """Die Argumente fuer ``ps5-dump-forge convert <Quelle> --to <Format>`` (rein, ohne Start - das ist testbar).

    ``format`` ist ``pkg`` (Vorgabe; dann gilt ``kraken``) oder eines der Abbildformate :data:`ABBILD_ZIELE`; fuer ``ffpfsc``
    nimmt ``stufe`` (0 bis 9) die zlib-Stufe (``--level``). Ein Paket (``.pkg``) als Quelle liest Forge im Strom - es wird
    nichts entpackt (gemessen 17.11.2026: ``.pkg`` -> ``.ffpkg``, ``.exfat`` und Ordner ohne Zwischenordner).

    ``entpacken``: ``"lz4"`` oder ``"zstd"`` - die Quelle ist so gepackt, und Forge entpackt die Packs, **waehrend** es das Paket
    schreibt (``--lz4-unpack`` / ``--zstd-unpack``: ein Auftrag, im Strom, ohne Zwischenordner; die Laufzeit der Packs
    wird durch die Fassung 0.4.2.1 ersetzt, ``ampr_emu.index`` neu geschrieben). So macht es Forge selbst (Reiter "Pack",
    Aktion "Unpack", Ziel ``.pkg``); ohne die Option traegt die Umwandlung die Packs als gewoehnliche Dateien ins Paket,
    und ein solches FPKG laeuft an der PS5 nicht (mit Kraken Mount). Gemessen am 18.11.2026 (Forge 0.5.6, 250-MB-Spiel): aus
    dem zstd- wie aus dem LZ4-gepackten Ordner entsteht mit der Option ein Paket gleicher Groesse (164'412'910 Byte, 58 Dateien)
    wie aus dem ungepackten Spiel; ohne sie 170'236'756 Byte in 44 Dateien (die Packs).
    """
    if format != "pkg" and format not in ABBILD_ZIELE:
        raise wz.Fehler("Unbekanntes Zielformat: %s" % format)
    if kraken not in KRAKEN_STUFEN:
        raise wz.Fehler("Unbekannte Kompressionsstufe: %s" % kraken)
    if entpacken and entpacken not in ENTPACK_VERFAHREN:
        raise wz.Fehler("Unbekanntes Packverfahren: %s" % entpacken)
    argumente = ["convert", quelle, "--to", format, "-o", ziel]
    if entpacken:
        argumente.append("--%s-unpack" % entpacken)
    if format == "pkg":
        argumente += ["--kraken", kraken]
    elif format == "ffpfsc" and stufe is not None and 0 <= int(stufe) <= 9:
        argumente += ["--level", str(int(stufe))]
    if int(kerne) > 0:
        argumente += ["--threads", str(int(kerne))]
    if voll_pruefen:
        argumente.append("--full-verify")
    if backport_entfernen:
        argumente.append("--remove-backport")
    return argumente


def _fehlertext(ausgabe: str) -> str:
    """Der Fehlersatz aus der Ausgabe: Forges ``failed: ...``/``ps5-dump-forge: ...``-Zeile, sonst die letzten Zeilen."""
    zeilen = [z.strip() for z in str(ausgabe).splitlines() if z.strip() and not z.lstrip().startswith(_EREIGNIS_ANFANG)]
    for z in reversed(zeilen):
        if z.startswith("ps5-dump-forge: failed:"):
            return z.split("failed:", 1)[1].strip()
    for z in reversed(zeilen):
        if z.startswith("ps5-dump-forge:"):
            return z.split(":", 1)[1].strip()
    return " | ".join(zeilen[-3:]) or "Dump Forge meldet einen Fehler ohne Text."


#: Wie Dump Forge einen Spielordner ablehnt, der Eintraege enthaelt, die sich nicht umwandeln lassen (``scan.rs``, gemessen 19.11.2026 an der
#: echten Befehlszeile): erst "<Ordner> holds entries that cannot be converted:", dann je Eintrag eine Zeile "  <Art>: <Pfad>", bei vielen
#: gekuerzt mit "  <Art>: ... and N more". Der Wortlaut ist englisch; :func:`fehler_verstaendlich` uebersetzt ihn.
SCAN_KOPF = re.compile(r"^(?:\w+: )?(?P<ordner>.+?) holds entries that cannot be converted:\s*$")
SCAN_MEHR = re.compile(r"^\.\.\. and (?P<n>\d+) more$")
#: Forges Art -> Schluessel des Texts. Forge nennt auch einen Windows-Reparsepunkt (OneDrive-Platzhalter) "symlink (not followed)".
SCAN_ARTEN = {
    "symlink (not followed)": "ps5pkg.forge_scan_link",
    "name is not valid UTF-8": "ps5pkg.forge_scan_utf8",
    "name contains a backslash": "ps5pkg.forge_scan_backslash",
    "hard link (more than one name)": "ps5pkg.forge_scan_hardlink",
    "special file": "ps5pkg.forge_scan_special",
    "unreadable": "ps5pkg.forge_scan_unreadable",
}


def fehler_verstaendlich(text: str, t: "Callable[..., str]") -> str:
    """Forges Fehlertext in der Sprache des Fensters, wenn er die bekannte Liste "Eintraege, die sich nicht umwandeln lassen" ist.

    Jeder andere Text kommt unveraendert zurueck, ebenso eine Zeile mit einer Art, die Forge neu eingefuehrt hat. ``t`` ist die
    Uebersetzungsfunktion des Fensters (``t(schluessel, **werte)``).
    """
    zeilen = str(text).splitlines()
    kopf = SCAN_KOPF.match(zeilen[0].strip()) if zeilen else None
    if kopf is None:
        return text
    erg = [t("ps5pkg.forge_scan_kopf", ordner=kopf.group("ordner"))]
    for zeile in zeilen[1:]:
        art, trenner, rest = zeile.strip().partition(": ")
        schluessel = SCAN_ARTEN.get(art)
        if not trenner or schluessel is None:
            erg.append(zeile)                                  # eine unbekannte Art oder Folgezeile: so lassen, nichts verschlucken
            continue
        mehr = SCAN_MEHR.match(rest)
        # Die Zeile baut der Text der Sprache (``forge_scan_zeile``): Franzoesisch setzt ein Leerzeichen vor den Doppelpunkt. Forge kuerzt die Liste je
        # Art (``MAX_LISTED``), "... and N more" gehoert also zur Art davor.
        erg.append(t("ps5pkg.forge_scan_zeile", art=t(schluessel), rest=t("ps5pkg.forge_scan_mehr", n=mehr.group("n")) if mehr else rest))
    return "\n".join(erg)


class _Strom:
    """Liest Forges Zeilen: Ereignisse (JSON) nach dem Fenster, den Rest verwerfen oder als Fehlertext merken."""

    def __init__(self, zeile: "_Zeile | None", fortschritt: "Callable[[int, str], None] | None") -> None:
        self.zeile = zeile
        self.fortschritt = fortschritt
        self.ergebnis: "dict | None" = None      # Forges {"Ok": {...}} oder {"Err": "..."}
        self.stufen: list = []
        self._gruppen: dict = {}
        self.verworfen = 0

    def jede(self, text: str) -> None:
        if not text.startswith(_EREIGNIS_ANFANG):
            return                               # die Kurzfassung auf stderr: der Fehlertext kommt aus ``done``
        try:
            e = json.loads(text)
        except ValueError:
            return
        art = e.get("kind")
        if art == "stages":
            self.stufen = list(e.get("stages") or [])
        elif art == "progress" and self.fortschritt:
            gesamt = int(e.get("total", 0) or 0)
            prozent = min(99, int(int(e.get("done", 0) or 0) * 100 / gesamt)) if gesamt > 0 else 0
            self.fortschritt(prozent, str(e.get("stage", "") or ""))
        elif art == "log":
            self._protokoll(str(e.get("line", "") or ""))
        elif art == "done":
            self.ergebnis = e.get("result") if isinstance(e.get("result"), dict) else {}

    def _protokoll(self, zeile: str) -> None:
        if not zeile or not self.zeile:
            return
        for gruppe in _GRUPPEN:
            if zeile.startswith(gruppe):
                n = self._gruppen.get(gruppe, 0) + 1
                self._gruppen[gruppe] = n
                if n > _GRUPPE_ZEIGEN:
                    self.verworfen += 1
                    return
        self.zeile(zeile)

    def rest_melden(self) -> None:
        if self.verworfen and self.zeile:
            self.zeile("... und %d weitere Zeilen dieser Art" % self.verworfen)


def bauen(werkzeug: str, quelle: str, ziel: str, *, kraken: str = "fast", voll_pruefen: bool = False,
          backport_entfernen: bool = False, kerne: int = 0, zeile: "_Zeile | None" = None,
          fortschritt: "Callable[[int, str], None] | None" = None, abbruch: "_Abbruch | None" = None,
          popen_extra: "dict | None" = None, vorspann: "tuple[str, ...]" = (), format: str = "pkg",
          stufe: "int | None" = None, entpacken: str = "") -> ForgeBau:
    """Baut aus einem Spielordner oder Abbild ein Debug-Paket (``convert --to pkg``) und gibt das Ergebnis zurueck.

    Mit ``format`` eines der Abbildformate (:data:`ABBILD_ZIELE`) entsteht statt des Pakets ein Abbild - aus einem Ordner,
    einem Abbild oder einem ``.pkg``, im Strom und ohne Zwischenordner (``stufe``: zlib-Stufe fuer ``ffpfsc``).

    Args:
        ziel: Der vollstaendige Pfad der entstehenden ``.pkg`` (**Datei**). Forge schreibt zuerst ``<ziel>.<Kennung>.part``
            daneben, liest es zurueck und benennt es erst nach bestandener Pruefung um (``rename_no_replace``: eine
            vorhandene Datei wird nicht ersetzt - das Fenster fragt vorher).
        kraken: ``fast`` (Vorgabe), ``balanced``, ``smallest`` (~2,6 % kleiner, ~9-mal langsamer) oder ``stored``.
        voll_pruefen: ``--full-verify`` - das Ergebnis wird Byte fuer Byte gelesen (Vorgabe: Stichprobe).
        backport_entfernen: ``--remove-backport`` - die Backport-Bibliotheken aus ``fakelib/`` weglassen (bei einem gepackten
            Spiel nur zusammen mit ``entpacken``: Forge verweigert es sonst).
        entpacken: ``"lz4"`` oder ``"zstd"``: die Packs der Quelle beim Bauen entpacken (:func:`convert_argumente`).
        zeile: Protokollzeilen Forges (gruppierte Wiederholungen gekuerzt).
        fortschritt: ``(Prozent 0..99, Stufe)``; die Stufen heissen ``scan``, ``preflight``, ``check``, ``plan``,
            ``compress``, ``write``, ``verify``, ``finalize`` (``extract`` zuerst bei einem Archiv).
        vorspann: nur fuer Tests (``werkzeug`` ist dann der Python-Aufruf, ``vorspann`` das Skript).

    Raises:
        wz.Fehler: Forge scheitert (mit seinem Text), liefert kein Ergebnis oder die Ausgabedatei fehlt; ``abgebrochen``
            beim Abbruch (``wz.laufen`` beendet den Prozess samt Kindern; das Fenster raeumt die ``.part`` danach weg).
    """
    argumente = [*vorspann, *convert_argumente(quelle, ziel, kraken=kraken, voll_pruefen=voll_pruefen,
                                               backport_entfernen=backport_entfernen, kerne=kerne, format=format,
                                               stufe=stufe, entpacken=entpacken)]
    os.makedirs(os.path.dirname(os.path.abspath(ziel)) or ".", exist_ok=True)
    strom = _Strom(zeile, fortschritt)
    rc, aus = wz.laufen(werkzeug, argumente, zeile=strom.jede, abbruch=abbruch, popen_extra=popen_extra)
    if rc == -1:
        raise wz.Fehler("abgebrochen")
    strom.rest_melden()
    ergebnis = strom.ergebnis
    if ergebnis is not None and "Err" in ergebnis:
        raise wz.Fehler(str(ergebnis["Err"]))
    if rc != 0:
        raise wz.Fehler(_fehlertext(aus))
    if ergebnis is None or not isinstance(ergebnis.get("Ok"), dict):
        raise wz.Fehler("Dump Forge meldet kein Ergebnis: %s" % _fehlertext(aus))
    ok = ergebnis["Ok"]
    pruef = ok.get("verify") if isinstance(ok.get("verify"), dict) else {}
    pfad = str(ok.get("output", "") or ziel)
    if not os.path.isfile(pfad):
        raise wz.Fehler("Dump Forge meldet Erfolg, aber die Ausgabedatei fehlt: %s" % pfad)
    return ForgeBau(
        pfad=pfad, bytes=int(ok.get("bytes", 0) or 0), dateien=int(ok.get("files", 0) or 0),
        pruefungen=[str(z) for z in (ok.get("checks") or [])], modus=str(pruef.get("mode", "fast") or "fast"),
        geprueft_bytes=int(pruef.get("checked_bytes", 0) or 0), gesamt_bytes=int(pruef.get("total_bytes", 0) or 0),
        proben=int(pruef.get("samples", 0) or 0))
