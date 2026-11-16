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

    Windows (auch arm64: laeuft dort als x64) = ``win-x64``; macOS (Apple Silicon und Intel gleichermassen) =
    ``macos-universal``; Linux nur auf x86-64 (``linux-x64``, statisch gegen musl gebunden).
    """
    if sys.platform == "win32":
        return "win-x64"
    if sys.platform == "darwin":
        return "macos-universal"
    if platform.machine().lower() in ("x86_64", "amd64"):
        return "linux-x64"
    return ""


def dateiname() -> str:
    return "ps5-dump-forge.exe" if sys.platform == "win32" else "ps5-dump-forge"


def werkzeug_suchen(wurzeln: "list[str] | None" = None) -> str:
    """Pfad zur Befehlszeile (``.exe`` unter Windows), sonst ``""`` - derselbe Suchweg wie bei ``ffpfsc-pkg-tool``."""
    unter = unterordner()
    if not unter:
        return ""
    for wurzel in wurzeln or []:
        kandidat = os.path.join(wurzel, ORDNER, unter, dateiname())
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


def lesen(werkzeug: str, pfad: str, arbeitsordner: "str | None" = None, *, abbruch: "_Abbruch | None" = None,
          popen_extra: "dict | None" = None, vorspann: "tuple[str, ...]" = ()) -> "wz.PaketInfo":
    """Liest ein Abbild (oder einen Spielordner) fuer die Anzeige: ``inspect --json`` und das Cover.

    Forge liest dazu nur, was es braucht (``param.json``, Cover, Dateiliste) - ein ``.exfat`` oder ``.ffpfsc`` wird
    nicht entpackt. ``vorspann`` steht nur fuer Tests (ein Skript statt der echten Befehlszeile).

    Raises:
        wz.Fehler: die Befehlszeile laesst sich nicht starten, liest die Quelle nicht oder antwortet nicht mit JSON.
    """
    rc, aus = wz.laufen(werkzeug, [*vorspann, "inspect", pfad, "--json"], abbruch=abbruch, popen_extra=popen_extra)
    if rc == -1:
        raise wz.Fehler("abgebrochen")
    if rc != 0:
        raise wz.Fehler(_fehlertext(aus))
    daten = wz._json_aus(aus)  # noqa: SLF001 - dieselbe Aufbereitung wie bei ffpfsc-pkg-tool
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


def convert_argumente(quelle: str, ziel: str, *, kraken: str = "fast", voll_pruefen: bool = False,
                      backport_entfernen: bool = False, kerne: int = 0) -> "list[str]":
    """Die Argumente fuer ``ps5-dump-forge convert <Quelle> --to pkg`` (rein, ohne Start - das ist testbar)."""
    if kraken not in KRAKEN_STUFEN:
        raise wz.Fehler("Unbekannte Kompressionsstufe: %s" % kraken)
    argumente = ["convert", quelle, "--to", "pkg", "-o", ziel, "--kraken", kraken]
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
          popen_extra: "dict | None" = None, vorspann: "tuple[str, ...]" = ()) -> ForgeBau:
    """Baut aus einem Spielordner oder Abbild ein Debug-Paket (``convert --to pkg``) und gibt das Ergebnis zurueck.

    Args:
        ziel: Der vollstaendige Pfad der entstehenden ``.pkg`` (**Datei**). Forge schreibt zuerst ``<ziel>.<Kennung>.part``
            daneben, liest es zurueck und benennt es erst nach bestandener Pruefung um (``rename_no_replace``: eine
            vorhandene Datei wird nicht ersetzt - das Fenster fragt vorher).
        kraken: ``fast`` (Vorgabe), ``balanced``, ``smallest`` (~2,6 % kleiner, ~9-mal langsamer) oder ``stored``.
        voll_pruefen: ``--full-verify`` - das Ergebnis wird Byte fuer Byte gelesen (Vorgabe: Stichprobe).
        backport_entfernen: ``--remove-backport`` - die Backport-Bibliotheken aus ``fakelib/`` weglassen.
        zeile: Protokollzeilen Forges (gruppierte Wiederholungen gekuerzt).
        fortschritt: ``(Prozent 0..99, Stufe)``; die Stufen heissen ``scan``, ``preflight``, ``check``, ``plan``,
            ``compress``, ``write``, ``verify``, ``finalize`` (``extract`` zuerst bei einem Archiv).
        vorspann: nur fuer Tests (``werkzeug`` ist dann der Python-Aufruf, ``vorspann`` das Skript).

    Raises:
        wz.Fehler: Forge scheitert (mit seinem Text), liefert kein Ergebnis oder die Ausgabedatei fehlt; ``abgebrochen``
            beim Abbruch (``wz.laufen`` beendet den Prozess samt Kindern; das Fenster raeumt die ``.part`` danach weg).
    """
    argumente = [*vorspann, *convert_argumente(quelle, ziel, kraken=kraken, voll_pruefen=voll_pruefen,
                                               backport_entfernen=backport_entfernen, kerne=kerne)]
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
