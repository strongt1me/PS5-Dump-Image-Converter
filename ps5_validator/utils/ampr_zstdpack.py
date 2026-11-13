"""zstd-Asset-Packs fuer ampr-emu-ng: ``ampr_zstd.index`` (AMPRZPK1) und ``ampr_zstd-NNN.pak`` (AMPRZDT1).

Das Format stammt aus ``docs/zstd.md`` und der Crate ``ps5-dump-forge-zstd`` von quer3q (GPL-3.0) sowie aus dem
Indexleser von ampr-emu-ng (``crates/ampr-format/src/zstd.rs``, GPL-3.0). Hier steht nur der Aufbau nach, Code wurde
nicht uebernommen. Gelesen werden zstd-Packs nur von der Laufzeit **ampr-emu-ng** (``libSceAmpr.sprx`` der Reihe NG);
die Laufzeit von drakmor kennt sie nicht und liest die LZ4-Packs (``ampr_assetpakete``).

Aufbau in Kuerze (alles little-endian, CRC-32 IEEE, Pfadhash FNV-1a 64 ueber den UTF-8-Pfad mit ``/``):

* Jede Datei zerfaellt in Chunks zu 256 KiB. Jeder Chunk ist ein eigener zstd-Frame (Inhaltsgroesse und Pruefsumme
  im Frame, kein Woerterbuch, Fenster hoechstens 256 KiB) oder, wenn zstd ihn nicht verkleinert, roh.
* Die Chunks liegen lueckenlos in den Bandateien, in der Reihenfolge der Dateien im Index (sortiert nach
  ``(Pfadhash, Pfad)``). Ein Band ist hoechstens 4 GiB minus 64 KiB gross; ein Chunk, der nicht mehr passt, beginnt das
  naechste Band. Die Kopfzeilen der Baender werden zuletzt geschrieben, dann der Index.

Was lose bleibt, bestimmt :func:`bleibt_lose` (Systemdateien: ``eboot.bin``, Module, ``sce_sys``, ``sce_module``,
``fakelib*``, jede ``.ini`` und die eigenen Dateien der Laufzeit). Alles andere, was nicht leer ist, wird gepackt - die
NG-Laufzeit bedient ein vollstaendig gepacktes Spiel.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import queue
import random
import struct
import threading
import uuid
import zlib
from array import array
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

from ps5_validator.utils.spielbaum import BaumFehler

try:  # pragma: no cover - die Bibliothek liegt dem Programm bei (requirements.txt)
    import zstandard as _zstd
except Exception:  # noqa: BLE001
    _zstd = None

INDEX_MAGIC = b"AMPRZPK1"
VOLUME_MAGIC = b"AMPRZDT1"
FORMAT_VERSION = 1
INDEX_NAME = "ampr_zstd.index"
VOLUME_PREFIX = "ampr_zstd-"
VOLUME_SUFFIX = ".pak"
CHUNK_SHIFT = 18
CHUNK_SIZE = 1 << CHUNK_SHIFT
#: So viel liest Packen und Pruefen auf einmal von der Platte (ein Vielfaches von ``CHUNK_SIZE``). Auf einer
#: USB-Festplatte kostet das Wechseln zwischen zwei Dateien je 256 KiB den Faktor 3-4 (gemessen 25,7 statt 95 MB/s);
#: je 4 MiB waren es 80 MB/s.
LESE_BLOCK = 8 << 20
#: Wie viele gelesene Stuecke dem Verdichten bzw. Vergleichen voraus sein duerfen (hoechstens ``LESE_BLOCK`` je Stueck).
LESE_VORLAUF = 4
VOLUME_LIMIT = (1 << 32) - (1 << 16)
INDEX_HEADER_SIZE = 128
VOLUME_HEADER_SIZE = 64
MAX_VOLUMES = 1 << 12
FILE_RECORD_SIZE = 32
CHUNK_RECORD_SIZE = 8
VOLUME_RECORD_SIZE = 8
STUFE_MIN = 1
STUFE_MAX = 22
#: Vorgabe wie in Forge ("schnell"); 9 = "mittel", 19 = "maximal".
STUFE_VORGABE = 5
STUFE_ANKER = (5, 9, 19)

CODEC_ROH = 0
CODEC_ZSTD = 1

#: Dateien der Laufzeit selbst - nie gepackt (die Laufzeit liest sie vor der Packschicht).
EMU_DATEIEN: tuple[str, ...] = (
    "ampr_assets.index", "ampr_assets.index.crc", "ampr_assets.index.runtime", "ampr_pack.toml",
    "ampr_emu.index", "fakelib/libSceAmpr.sprx", "ampr_commands.bin", "ampr_emu.log", "apr_emu.log",
)
#: Journal und Protokolle werden nicht mitgenommen (Forge laesst sie weg).
LAUFZEIT_PROTOKOLLE: tuple[str, ...] = ("ampr_emu.log", "apr_emu.log", "ampr_commands.bin")


class ZstdPackFehler(RuntimeError):
    """Packen, Pruefen oder Entpacken ist gescheitert; der Text ist fuer das Protokoll gedacht."""


Melder = Callable[[str], None]


def _stumm(_zeile: str) -> None:
    return None


def verfuegbar() -> bool:
    """Ob die ``zstandard``-Bibliothek geladen ist."""
    return _zstd is not None


def stufe_lesen(wert: Any, vorgabe: int = STUFE_VORGABE) -> int:
    """Eine zstd-Stufe 1 bis 22; alles andere ergibt die Vorgabe (kein stilles Abschneiden)."""
    try:
        zahl = int(str(wert).strip())
    except (TypeError, ValueError):
        return vorgabe
    return zahl if STUFE_MIN <= zahl <= STUFE_MAX else vorgabe


# ---------------------------------------------------------------------------
# Pfade und Namen
# ---------------------------------------------------------------------------
def pfadhash(pfad: bytes) -> int:
    """FNV-1a 64 ueber die Bytes des Pfads (Gross-/Kleinschreibung bleibt)."""
    h = 14695981039346656037
    for b in pfad:
        h = ((h ^ b) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def pfad_gueltig(pfad: str) -> bool:
    """Regeln des Formats: nicht leer, kein fuehrendes ``/``, kein ``\\`` oder NUL, keine leeren, ``.``- oder ``..``-Teile."""
    if not pfad or pfad.startswith("/") or "\\" in pfad or "\0" in pfad:
        return False
    if any(teil in ("", ".", "..") for teil in pfad.split("/")):
        return False
    try:
        return len(pfad.encode("utf-8")) <= 65535
    except UnicodeEncodeError:
        return False


def ziel_pfad(wurzel: str, rel: str) -> str:
    """Der Pfad einer Datei des Packs unterhalb von ``wurzel`` - oder :class:`ZstdPackFehler`, wenn er herausfuehrt.

    Der Index kommt aus einem fremden Spielordner und traegt nur Pruefsummen, keine Unterschrift; :func:`pfad_gueltig` folgt
    den Regeln des Formats und laesst deshalb einen Doppelpunkt durch. ``os.path.join(ziel, "C:", "x.dll")`` ergibt unter
    Windows aber ``C:x.dll`` - einen Pfad **ausserhalb** des Ziels (gefunden bei der Gesamtpruefung am 11.11.2026). Daher:
    unter Windows kein ``:`` in einem Pfadteil (auch kein NTFS-Datenstrom ``datei:strom``), und auf jedem System muss das
    Ergebnis unterhalb von ``wurzel`` liegen.

    Args:
        wurzel: Der Zielordner (wird absolut gemacht).
        rel: Der Pfad aus dem Index, mit ``/`` getrennt.
    """
    wurzel = os.path.normpath(os.path.abspath(wurzel))
    teile = rel.split("/")
    if os.name == "nt" and any(":" in t for t in teile):
        raise ZstdPackFehler("ampr_zstd.pfad_ausserhalb: %s" % rel)
    voll = os.path.normpath(os.path.join(wurzel, *teile))
    try:
        innen = os.path.commonpath([os.path.normcase(voll), os.path.normcase(wurzel)]) == os.path.normcase(wurzel)
    except ValueError:          # anderes Laufwerk
        innen = False
    if not innen or os.path.normcase(voll) == os.path.normcase(wurzel):
        raise ZstdPackFehler("ampr_zstd.pfad_ausserhalb: %s" % rel)
    return voll


def bandname(nummer: int) -> str:
    """``ampr_zstd-000.pak`` (mindestens drei Stellen)."""
    return "%s%03d%s" % (VOLUME_PREFIX, nummer, VOLUME_SUFFIX)


def ist_packname(rel: str) -> bool:
    """Ob ``rel`` (Wurzel des Spiels) der Index oder ein Band ist."""
    if rel == INDEX_NAME:
        return True
    return (rel.startswith(VOLUME_PREFIX) and rel.endswith(VOLUME_SUFFIX)
            and rel[len(VOLUME_PREFIX):-len(VOLUME_SUFFIX)].isdigit()
            and len(rel[len(VOLUME_PREFIX):-len(VOLUME_SUFFIX)]) >= 3)


def bleibt_lose(rel: str) -> bool:
    """Die Dateien, die nie in ein Pack gehen (Systemschicht und Laufzeit), ohne Beachtung der Schreibung.

    ``eboot.bin`` (jeder Ordner), ``.elf``/``.self``/``.prx``/``.sprx``, **jede ``.ini``** (``dlc_emu.ini`` und andere
    Einstellungen, die man von Hand aendert - seit ps5-dump-forge v0.5.5, 10.11.2026), alles in einem Wurzelordner
    ``sce_sys``, ``sce_module`` oder ``fakelib*`` und die Dateien der Laufzeit; dazu die Packdateien selbst.
    """
    klein = rel.lower()
    name = klein.rsplit("/", 1)[-1]
    erster = klein.split("/", 1)[0]
    if name == "eboot.bin" or klein.endswith((".elf", ".self", ".prx", ".sprx", ".ini")):
        return True
    if "/" in klein and (erster in ("sce_sys", "sce_module") or erster.startswith("fakelib")):
        return True
    if klein in {n.lower() for n in EMU_DATEIEN} or klein == "ampr_emu.index":
        return True
    return ist_packname(rel)


@dataclass
class Auswahl:
    """Was ein Lauf packt und was lose bleibt."""

    gepackt: list[tuple[str, int]] = field(default_factory=list)   # (Pfad, Groesse)
    lose: list[tuple[str, int]] = field(default_factory=list)
    leer: list[str] = field(default_factory=list)
    ungueltig: list[str] = field(default_factory=list)
    #: Wie viele Dateien nur wegen der eigenen Regeln lose bleiben.
    nach_regeln_lose: int = 0

    @property
    def gepackte_bytes(self) -> int:
        return sum(g for _p, g in self.gepackt)


PROFIL_MAX_BYTES = 1024 * 1024
_AKTIONEN = ("compress", "store", "loose")


@dataclass
class Regeln:
    """Eigene Packregeln aus einer TOML-Datei (Format wie ``ampr_pack.py`` / Lazy_AMPR, wie bei Forge gelesen).

    ``[pack] default_action`` (compress, store, loose; Vorgabe loose) gilt fuer Dateien, die keine Regel trifft.
    Jede ``[[rule]]`` hat ``action`` (Vorgabe compress), ``include`` (Glob oder Liste, Vorgabe ``**``) und ``exclude``;
    die **letzte** treffende Regel gewinnt. Globs sind ``fnmatchcase`` (gross/klein beachtet, ``*`` trifft auch ``/``).
    Bei zstd packt ``store`` wie ``compress`` (ein Chunk, den zstd nicht verkleinert, bleibt ohnehin roh); Blockgroesse,
    ``hot`` und ``layout`` haben keine Wirkung. ``include_from`` / ``exclude_from`` (Musterdateien neben der Regeldatei)
    gelten wie bei Forge ab v0.5.4. Alle anderen Schluessel werden ignoriert, wie bei Forge.
    """

    standard: str = "loose"
    regeln: "list[tuple[str, list[str], list[str]]]" = field(default_factory=list)
    ignoriert: list[str] = field(default_factory=list)
    quelle: str = ""
    #: Aus den Regeln abgeleitet (erst beim ersten :meth:`aktion` gebaut): je Regel Aktion, genaue Pfade (Menge)
    #: und Globs getrennt, damit lange Mustertexte aus ``include_from`` nicht je Datei durchprobiert werden.
    _vorbereitet: Any = field(default=None, repr=False, compare=False)

    def aktion(self, rel: str) -> str:
        import fnmatch
        if self._vorbereitet is None:
            def teilen(muster: list[str]) -> "tuple[set[str], list[str]]":
                exakt = {m for m in muster if not _hat_platzhalter(m)}
                return exakt, [m for m in muster if _hat_platzhalter(m)]
            self._vorbereitet = [(a, *teilen(e), *teilen(x)) for a, e, x in self.regeln]
        ergebnis = self.standard
        for aktion, ein_exakt, ein_globs, aus_exakt, aus_globs in self._vorbereitet:
            if (rel in ein_exakt or any(fnmatch.fnmatchcase(rel, m) for m in ein_globs)) and \
                    not (rel in aus_exakt or any(fnmatch.fnmatchcase(rel, m) for m in aus_globs)):
                ergebnis = aktion
        return ergebnis


def _hat_platzhalter(muster: str) -> bool:
    return any(c in muster for c in "*?[")


def _muster_liste(wert: Any, name: str) -> list[str]:
    if isinstance(wert, str):
        wert = [wert]
    if not isinstance(wert, list) or not all(isinstance(m, str) for m in wert):
        raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s muss ein Muster oder eine Liste von Mustern sein" % name)
    return [m.replace("\\", "/").lstrip("/") for m in wert]


#: Grenzen fuer Musterdateien (``include_from`` / ``exclude_from``), wie bei ps5-dump-forge v0.5.4: je Datei 1 MiB,
#: zusammen 16 MiB und 200.000 Muster, davon hoechstens 10.000 mit Platzhalter (Globs werden je Datei durchprobiert).
MUSTERDATEI_MAX_BYTES = 1024 * 1024
MUSTER_MAX_BYTES_GESAMT = 16 * 1024 * 1024
MUSTER_MAX_ANZAHL = 200_000
MUSTER_MAX_GLOBS = 10_000


@dataclass
class _MusterZaehler:
    bytes_gesamt: int = 0
    muster: int = 0
    globs: int = 0


def _muster_dateien(ordner: str, wert: Any, name: str, nummer: int, zaehler: _MusterZaehler) -> list[str]:
    """Liest die Musterdateien einer Regel. Namen liegen relativ zum Ordner der Regeldatei und bleiben darin.

    Ein Muster je Zeile (getrimmt); leere Zeilen und Zeilen mit ``#`` am Anfang fallen weg. Absolute Namen, ``.``,
    ``..``, ``\\`` und ``:`` sind verboten, ebenso Verknuepfungen, die aus dem Ordner hinausfuehren.
    """
    if wert is None:
        return []
    if isinstance(wert, str):
        wert = [wert]
    if not isinstance(wert, list) or not all(isinstance(n, str) for n in wert):
        raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s (Regel %d) muss ein Dateiname oder eine Liste sein"
                             % (name, nummer))
    wurzel = os.path.realpath(ordner)
    ergebnis: list[str] = []
    for datei in wert:
        teile = datei.split("/")
        if (not datei or "\\" in datei or ":" in datei or datei.startswith("/")
                or any(t in ("", ".", "..") for t in teile)):
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s (Regel %d): %r ist kein Pfad innerhalb des Regelordners"
                                 % (name, nummer, datei))
        voll = os.path.join(ordner, *teile)
        echt = os.path.realpath(voll)
        if os.path.islink(voll) or not os.path.isfile(voll) or os.path.commonpath([wurzel, echt]) != wurzel:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s (Regel %d): %s ist keine normale Datei im Regelordner"
                                 % (name, nummer, datei))
        groesse = os.path.getsize(voll)
        if groesse > MUSTERDATEI_MAX_BYTES:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s ist groesser als 1 MiB" % datei)
        zaehler.bytes_gesamt += groesse
        if zaehler.bytes_gesamt > MUSTER_MAX_BYTES_GESAMT:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: die Musterdateien sind zusammen groesser als 16 MiB")
        try:
            with open(voll, "rb") as fh:
                text = fh.read().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s: %s" % (datei, exc)) from exc
        for zeile in text.splitlines():
            muster = zeile.strip()
            if not muster or muster.startswith("#"):
                continue
            zaehler.muster += 1
            if _hat_platzhalter(muster):
                zaehler.globs += 1
            if zaehler.muster > MUSTER_MAX_ANZAHL or zaehler.globs > MUSTER_MAX_GLOBS:
                raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: zu viele Muster in den Musterdateien")
            ergebnis.append(muster.replace("\\", "/").lstrip("/"))
    return ergebnis


def regeln_laden(pfad: str) -> Regeln:
    """Liest und prueft eine Regeldatei; jeder Fehler ist ein :class:`ZstdPackFehler` (nichts wird geschrieben)."""
    import tomllib
    try:
        if os.path.islink(pfad) or not os.path.isfile(pfad):
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: keine normale Datei")
        if os.path.getsize(pfad) > PROFIL_MAX_BYTES:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: groesser als 1 MiB")
        with open(pfad, "rb") as fh:
            daten = tomllib.loads(fh.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: %s" % exc) from exc
    ergebnis = Regeln(quelle=pfad)
    pack = daten.get("pack", {})
    if not isinstance(pack, dict):
        raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: [pack] ist keine Tabelle")
    standard = str(pack.get("default_action", "loose")).strip().lower()
    if standard not in _AKTIONEN:
        raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: default_action %r" % standard)
    ergebnis.standard = standard
    ergebnis.ignoriert += ["pack." + k for k in pack if k != "default_action"]
    regeln = daten.get("rule", [])
    if not isinstance(regeln, list) or not all(isinstance(r, dict) for r in regeln):
        raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: rule muss [[rule]] sein")
    ordner = os.path.dirname(os.path.abspath(pfad))
    zaehler = _MusterZaehler()
    for nummer, regel in enumerate(regeln, 1):
        aktion = str(regel.get("action", "compress")).strip().lower()
        if aktion not in _AKTIONEN:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: action %r in Regel %d" % (aktion, nummer))
        aus_dateien_ein = _muster_dateien(ordner, regel.get("include_from"), "include_from", nummer, zaehler)
        aus_dateien_aus = _muster_dateien(ordner, regel.get("exclude_from"), "exclude_from", nummer, zaehler)
        if "include" in regel:
            einschluss = _muster_liste(regel["include"], "include") + aus_dateien_ein
        else:
            # Wie bei ampr_pack.py: Hat die Regel Musterdateien mit Inhalt, entfaellt die Vorgabe ``**``.
            einschluss = aus_dateien_ein or ["**"]
        if not einschluss:
            raise ZstdPackFehler("ampr_zstd.regeln_ungueltig: leeres include in Regel %d" % nummer)
        ausschluss = _muster_liste(regel.get("exclude", []), "exclude") + aus_dateien_aus
        ergebnis.regeln.append((aktion, einschluss, ausschluss))
        ergebnis.ignoriert += ["rule." + k for k in regel
                               if k not in ("action", "include", "exclude", "include_from", "exclude_from")]
    ergebnis.ignoriert += [k for k in daten if k not in ("pack", "rule")]
    ergebnis.ignoriert = sorted(set(ergebnis.ignoriert))
    return ergebnis


def dateien_auswaehlen(app0: str, abbruch: Callable[[], bool] = lambda: False,
                       regeln: "Regeln | None" = None, melden: "Callable[[str], None] | None" = None) -> Auswahl:
    """Geht den Spielordner durch und teilt die Dateien in gepackt / lose.

    ``melden(pfad)`` wird vor dem Durchgang gerufen: Bei einem grossen Spiel braucht schon das Auflisten Sekunden
    (5.103 Dateien auf einem Laufwerk: 0,65 s warm, 7 s kalt; Ghost of Yotei mit 84.218 Dateien rund 20 s kalt).

    Ohne ``regeln`` wird alles gepackt, was nicht Systemdatei oder leer ist. Mit ``regeln`` entscheiden diese
    ueber die uebrigen Dateien; Systemdateien, Laufzeitdateien, Packdateien und leere Dateien bleiben immer lose.
    """
    wurzel = os.path.abspath(app0)
    ergebnis = Auswahl()
    if melden is not None:
        melden(wurzel)
    for ordner, unter, dateien in os.walk(wurzel):
        if abbruch():
            raise ZstdPackFehler("ampr_pack.abgebrochen")
        unter.sort()
        for name in sorted(dateien):
            voll = os.path.join(ordner, name)
            rel = os.path.relpath(voll, wurzel).replace(os.sep, "/")
            if os.path.islink(voll) or not os.path.isfile(voll):
                ergebnis.lose.append((rel, 0))
                continue
            _einordnen(ergebnis, rel, os.path.getsize(voll), regeln)
    # Ein Dateipfad darf nicht der Ordner einer anderen sein - im Dateisystem ausgeschlossen, hier nur zur Sicherheit.
    return ergebnis


def _einordnen(ergebnis: Auswahl, rel: str, groesse: int, regeln: "Regeln | None") -> None:
    """Sortiert eine Datei in ``gepackt`` oder ``lose`` (und ``leer``/``ungueltig``); die Regeln der Auswahl in einer Stelle."""
    if bleibt_lose(rel):
        ergebnis.lose.append((rel, groesse))
    elif groesse == 0:
        ergebnis.leer.append(rel)
        ergebnis.lose.append((rel, 0))
    elif not pfad_gueltig(rel):
        ergebnis.ungueltig.append(rel)
        ergebnis.lose.append((rel, groesse))
    elif regeln is not None and regeln.aktion(rel) == "loose":
        ergebnis.lose.append((rel, groesse))
        ergebnis.nach_regeln_lose += 1
    else:
        ergebnis.gepackt.append((rel, groesse))


def auswahl_aus_liste(dateien: "Sequence[tuple[str, int]]", abbruch: Callable[[], bool] = lambda: False,
                      regeln: "Regeln | None" = None) -> Auswahl:
    """Wie :func:`dateien_auswaehlen`, aber aus einer Liste ``(Pfad, Groesse)`` - etwa der eines Lesebaums (``spielbaum``).

    Die Liste wird so geordnet wie der Gang durch einen Ordner (je Ordner erst die Dateien, dann die Unterordner, jeweils nach
    Namen), damit beide Wege dieselbe Auswahl in derselben Reihenfolge liefern.
    """
    def schluessel(eintrag: "tuple[str, int]") -> "tuple[tuple[str, ...], str]":
        teile = eintrag[0].split("/")
        return tuple(teile[:-1]), teile[-1]

    ergebnis = Auswahl()
    for rel, groesse in _ordner_reihenfolge(dateien, schluessel):
        if abbruch():
            raise ZstdPackFehler("ampr_pack.abgebrochen")
        _einordnen(ergebnis, rel, groesse, regeln)
    return ergebnis


def _ordner_reihenfolge(dateien: "Sequence[tuple[str, int]]", schluessel: Callable) -> "list[tuple[str, int]]":
    """Die Reihenfolge von ``os.walk`` mit sortierten Namen: ein Ordner zuerst mit seinen Dateien, dann seine Unterordner."""
    baum: dict[tuple[str, ...], list[tuple[str, int]]] = {}
    kinder: dict[tuple[str, ...], set[str]] = {}
    for eintrag in dateien:
        ordner = schluessel(eintrag)[0]
        baum.setdefault(ordner, []).append(eintrag)
        for i in range(len(ordner)):                            # auch Ordner, die nur Unterordner enthalten
            kinder.setdefault(ordner[:i], set()).add(ordner[i])
    ergebnis: list[tuple[str, int]] = []
    stapel: list[tuple[str, ...]] = [()]
    while stapel:                                               # ohne Rekursion: Pfade koennen tief sein
        ordner = stapel.pop()
        ergebnis.extend(sorted(baum.get(ordner, ()), key=lambda e: e[0].split("/")[-1]))
        stapel.extend(ordner + (name,) for name in sorted(kinder.get(ordner, ()), reverse=True))
    return ergebnis


# ---------------------------------------------------------------------------
# Chunks verdichten
# ---------------------------------------------------------------------------
def _kompressor(stufe: int):
    if _zstd is None:
        raise ZstdPackFehler("ampr_zstd.bibliothek_fehlt")
    parameter = _zstd.ZstdCompressionParameters.from_level(
        stufe, window_log=CHUNK_SHIFT, write_checksum=True, write_content_size=True)
    return _zstd.ZstdCompressor(compression_params=parameter)


def chunk_verdichten(daten: bytes, stufe: int, kompressor=None) -> tuple[int, bytes]:
    """Ein Chunk: ``(Codec, gespeicherte Bytes)``. zstd nur, wenn es den Chunk **strikt** verkleinert."""
    kompressor = kompressor or _kompressor(stufe)
    frame = kompressor.compress(daten)
    if len(frame) < len(daten):
        return CODEC_ZSTD, frame
    return CODEC_ROH, daten


def chunk_entpacken(codec: int, gespeichert: bytes, erwartet: int) -> bytes:
    """Gegenstueck: gibt die ``erwartet`` Bytes zurueck oder wirft :class:`ZstdPackFehler`."""
    if codec == CODEC_ROH:
        if len(gespeichert) != erwartet:
            raise ZstdPackFehler("roher Chunk hat die falsche Laenge")
        return gespeichert
    if codec != CODEC_ZSTD or _zstd is None:
        raise ZstdPackFehler("unbekannter Codec")
    try:
        rueckgabe = _zstd.ZstdDecompressor(max_window_size=CHUNK_SIZE).decompress(
            gespeichert, max_output_size=erwartet)
    except Exception as exc:  # noqa: BLE001 - jede Bibliotheksausnahme ist ein beschaedigter Frame
        raise ZstdPackFehler("zstd-Frame beschaedigt: %s" % exc) from exc
    if len(rueckgabe) != erwartet:
        raise ZstdPackFehler("zstd-Frame hat die falsche Laenge")
    return rueckgabe


def rahmen_pruefen(frame: bytes, erwartet: int) -> None:
    """Prueft die Vorgaben des Formats an einem Frame: Inhaltsgroesse, Pruefsumme, Fenster, kein Woerterbuch."""
    if _zstd is None:
        raise ZstdPackFehler("ampr_zstd.bibliothek_fehlt")
    p = _zstd.get_frame_parameters(frame)
    if p.content_size != erwartet or not p.has_checksum or p.dict_id != 0 or p.window_size > CHUNK_SIZE:
        raise ZstdPackFehler("zstd-Frame entspricht nicht dem Format")


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------
class _Vorlauf:
    """Fuehrt einen Erzeuger in einem eigenen Faden aus (Lesevorlauf).

    Die Platte arbeitet so durch, waehrend der Aufrufer verdichtet, entpackt oder schreibt. Die Ergebnisse kommen in
    der Reihenfolge des Erzeugers an; ein Fehler des Erzeugers wird beim Abholen im Aufrufer ausgeloest. Die Warteschlange
    ist klein und damit der Speicher begrenzt. Immer mit :meth:`schliessen` beenden (auch nach einem Fehler).
    """

    def __init__(self, erzeuger: Iterator[Any], tiefe: int = LESE_VORLAUF) -> None:
        self._schlange: "queue.Queue[tuple[int, Any]]" = queue.Queue(maxsize=max(1, tiefe))
        self._halt = threading.Event()
        self._faden = threading.Thread(target=self._laufen, args=(erzeuger,), name="ampr-zstd-lesen", daemon=True)
        self._faden.start()

    def _ablegen(self, eintrag: "tuple[int, Any]") -> bool:
        while not self._halt.is_set():
            try:
                self._schlange.put(eintrag, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def _laufen(self, erzeuger: Iterator[Any]) -> None:
        try:
            for stueck in erzeuger:
                if not self._ablegen((0, stueck)):
                    return
            self._ablegen((2, None))
        except BaseException as exc:  # noqa: BLE001 - jeder Fehler gehoert dem Aufrufer
            self._ablegen((1, exc))
        finally:
            schliessen = getattr(erzeuger, "close", None)
            if schliessen is not None:
                try:
                    schliessen()
                except Exception:  # noqa: BLE001
                    pass

    def __iter__(self) -> Iterator[Any]:
        while True:
            art, wert = self._schlange.get()
            if art == 0:
                yield wert
            elif art == 1:
                raise wert
            else:
                return

    def schliessen(self) -> None:
        self._halt.set()
        self._faden.join(timeout=10)


class _BandPuffer:
    """Liest eine Bandatei in grossen Bloecken. Chunks in aufsteigender Reihenfolge kosten so keinen Zugriff je Chunk."""

    def __init__(self, fh: Any) -> None:
        self._fh = fh
        self._start = 0
        self._daten = b""

    def lesen(self, offset: int, laenge: int) -> bytes:
        """``laenge`` Bytes ab ``offset``; kuerzer nur am Dateiende."""
        a = offset - self._start
        if 0 <= a and a + laenge <= len(self._daten):
            return self._daten[a:a + laenge]
        self._fh.seek(offset)
        self._daten = self._fh.read(max(LESE_BLOCK, laenge))
        self._start = offset
        return self._daten[:laenge]


def _datei_bloecke(pfad: str, groesse: int) -> Iterator[list[bytes]]:
    """Liest eine Datei in Stuecken zu ``LESE_BLOCK`` Bytes; je Stueck kommen deren Chunks (256 KiB, der letzte kuerzer)."""
    gelesen = 0
    with open(pfad, "rb") as fh:
        while gelesen < groesse:
            menge = min(LESE_BLOCK, groesse - gelesen)
            daten = fh.read(menge)
            if len(daten) < menge:
                raise ZstdPackFehler("%s ist kuerzer als gemeldet" % pfad)
            gelesen += menge
            yield [daten[i:i + CHUNK_SIZE] for i in range(0, menge, CHUNK_SIZE)]
        if fh.read(1):
            raise ZstdPackFehler("%s ist waehrend des Packens gewachsen" % pfad)


def _chunk_wort(offset: int, band: int, gespeichert: int, codec: int) -> int:
    if not (VOLUME_HEADER_SIZE <= offset and offset + gespeichert <= VOLUME_LIMIT and 0 < gespeichert <= CHUNK_SIZE
            and 0 <= band < MAX_VOLUMES):
        raise ZstdPackFehler("Chunk passt nicht in die Beschreibung")
    return offset | (band << 32) | ((gespeichert - 1) << 44) | (codec << 62)


def _crc(daten: bytes) -> int:
    return zlib.crc32(daten) & 0xFFFFFFFF


def _bandkopf(nummer: int, anzahl: int, archiv: bytes, groesse: int) -> bytes:
    kopf = bytearray(VOLUME_HEADER_SIZE)
    kopf[0:8] = VOLUME_MAGIC
    struct.pack_into("<IIII", kopf, 8, FORMAT_VERSION, VOLUME_HEADER_SIZE, nummer, anzahl)
    kopf[24:40] = archiv
    struct.pack_into("<Q", kopf, 40, groesse - VOLUME_HEADER_SIZE)
    struct.pack_into("<I", kopf, 60, _crc(bytes(kopf[:60]) + b"\0\0\0\0"))
    return bytes(kopf)


@dataclass
class Ergebnis:
    """Zusammenfassung eines Packlaufs."""

    dateien: int = 0
    chunks: int = 0
    zstd_chunks: int = 0
    roh_chunks: int = 0
    logische_bytes: int = 0
    gespeicherte_bytes: int = 0
    baender: list[str] = field(default_factory=list)
    index: str = ""
    stufe: int = STUFE_VORGABE
    archiv_id: bytes = b""
    #: CRC-32 der Quellbytes je Chunk, in der Reihenfolge des Index (``pruefen(summen=...)`` liest die Quelle dann nicht mehr).
    pruefsummen: "array[int]" = field(default_factory=lambda: array("I"))


def archiv_id_ableiten(auswahl: Auswahl, stufe: int = STUFE_VORGABE) -> bytes:
    """Eine Archiv-ID, die nur von der Dateiliste (Pfad, Groesse) und der Stufe abhaengt.

    Die Kennung steht in jedem Band und im Index. Mit einer zufaelligen (``packen`` nimmt eine) ergaebe dieselbe Quelle bei
    jedem Lauf ein anderes Abbild; mit dieser ist es byteweise dasselbe (Stufe 3: reproduzierbares Abbild wie bei Forge).
    """
    h = hashlib.sha256(b"AMPRZSTD-archiv\0%d\0" % stufe_lesen(stufe))
    for rel, groesse in sorted(auswahl.gepackt):
        h.update(rel.encode("utf-8") + b"\0" + str(groesse).encode("ascii") + b"\0")
    return h.digest()[:16]


class _Plan:
    """Die Bandaufteilung und der Index: Aus der Folge der Chunks (Codec, gespeicherte Laenge) folgt, welcher Chunk in welches
    Band an welche Stelle kommt und wie der Index aussieht.

    Das Packen in einen Ordner, der Messdurchgang und der Schreibdurchgang (Strom ohne Zwischenordner) rechnen alle damit.
    Der Schreibdurchgang muss genau das Ergebnis des Messdurchgangs wiederholen; was beide gemeinsam haben, steht nur hier.
    """

    def __init__(self, auswahl: Auswahl, stufe: int, archiv: bytes) -> None:
        eintraege = []
        for rel, groesse in auswahl.gepackt:
            roh = rel.encode("utf-8")
            eintraege.append((pfadhash(roh), roh, rel, groesse))
        eintraege.sort(key=lambda e: (e[0], e[1]))
        if any(a[0] == b[0] and a[1] == b[1] for a, b in zip(eintraege, eintraege[1:])):
            raise ZstdPackFehler("ampr_zstd.pfad_doppelt")
        self.eintraege = eintraege
        self.stufe = stufe
        self.archiv = archiv
        self.chunkwoerter: list[int] = []
        self.dateisaetze: list[bytes] = []
        self.strings = bytearray()
        self.baeume: list[int] = []                        # Groesse je Band (mit Kopf), erst fuer abgeschlossene Baender
        self.summen = array("I")                           # CRC-32 der Quellbytes je Chunk, in der Reihenfolge des Index
        self.ergebnis = Ergebnis(stufe=stufe, archiv_id=archiv)
        self.band = -1
        self.offset = VOLUME_HEADER_SIZE
        self.erster_chunk = 0
        self.erledigt = 0
        self.gesamt = max(1, auswahl.gepackte_bytes)
        self._band_beginnt()

    def _band_beginnt(self) -> None:
        if self.band + 1 >= MAX_VOLUMES:
            raise ZstdPackFehler("ampr_zstd.zu_viele_baender")
        self.band += 1
        self.offset = VOLUME_HEADER_SIZE
        self.ergebnis.baender.append(bandname(self.band))

    def datei_beginnt(self, nummer: int) -> None:
        _h, roh, _rel, groesse = self.eintraege[nummer]
        pfad_off = len(self.strings)
        self.strings += roh
        self.dateisaetze.append(struct.pack("<QQIIHHI", _h, groesse, self.erster_chunk, pfad_off, len(roh), 0, 0))
        self.erster_chunk += -(-groesse // CHUNK_SIZE)
        self.ergebnis.dateien += 1
        self.ergebnis.logische_bytes += groesse

    def chunk(self, rohlaenge: int, codec: int, gespeichert: int, summe: int) -> bool:
        """Verbucht einen Chunk; ``True``, wenn er ein neues Band beginnt (das alte ist dann abgeschlossen)."""
        neu = False
        if self.offset + gespeichert > VOLUME_LIMIT:
            self.baeume.append(self.offset)
            self._band_beginnt()
            neu = True
        self.summen.append(summe)
        self.chunkwoerter.append(_chunk_wort(self.offset, self.band, gespeichert, codec))
        self.offset += gespeichert
        self.ergebnis.chunks += 1
        self.ergebnis.gespeicherte_bytes += gespeichert
        if codec == CODEC_ZSTD:
            self.ergebnis.zstd_chunks += 1
        else:
            self.ergebnis.roh_chunks += 1
        self.erledigt += rohlaenge
        return neu

    def ende(self) -> None:
        """Schliesst das letzte Band ab; danach stehen ``baeume`` und der Index fest."""
        self.baeume.append(self.offset)
        self.ergebnis.index = INDEX_NAME
        self.ergebnis.pruefsummen = self.summen

    def anteil(self) -> float:
        return min(1.0, self.erledigt / self.gesamt)

    def bandkopf(self, nummer: int) -> bytes:
        return _bandkopf(nummer, len(self.baeume), self.archiv, self.baeume[nummer])

    def index(self) -> bytes:
        """Der ganze Inhalt von ``ampr_zstd.index``."""
        dateien_tab = b"".join(self.dateisaetze)
        chunks_tab = b"".join(struct.pack("<Q", w) for w in self.chunkwoerter)
        baender_tab = b"".join(struct.pack("<Q", g) for g in self.baeume)
        files_off = INDEX_HEADER_SIZE
        chunks_off = files_off + len(dateien_tab)
        volumes_off = chunks_off + len(chunks_tab)
        strings_off = volumes_off + len(baender_tab)
        nutzlast = dateien_tab + chunks_tab + baender_tab + bytes(self.strings)
        kopf = bytearray(INDEX_HEADER_SIZE)
        kopf[0:8] = INDEX_MAGIC
        struct.pack_into("<IIBBH", kopf, 8, FORMAT_VERSION, INDEX_HEADER_SIZE, CHUNK_SHIFT, self.stufe, 0)
        struct.pack_into("<I", kopf, 20, len(self.baeume))
        kopf[24:40] = self.archiv
        struct.pack_into("<QQQQQQQQ", kopf, 40, len(self.eintraege), len(self.chunkwoerter), files_off, chunks_off,
                         volumes_off, strings_off, len(self.strings), self.ergebnis.logische_bytes)
        struct.pack_into("<I", kopf, 112, _crc(nutzlast))
        struct.pack_into("<I", kopf, 116, _crc(bytes(kopf[:112]) + b"\0" * 8 + bytes(kopf[120:])))
        return bytes(kopf) + nutzlast


def _arbeiterzahl(arbeiter: int) -> int:
    arbeiter = arbeiter if arbeiter and arbeiter > 0 else (os.cpu_count() or 2)
    return max(1, min(arbeiter, 32))


def _chunk_folge(eintraege: list, bloecke_fuer: "Callable[[str, int], Iterator[list[bytes]]]", stufe: int, arbeiter: int,
                 abbruch: Callable[[], bool]) -> "Iterator[tuple]":
    """Liest die Quellen, verdichtet auf mehreren Faeden und liefert in der Reihenfolge des Index:

    * ``("datei", nummer)`` - die Datei ``nummer`` (Index der Eintraege) beginnt,
    * ``("chunk", rohlaenge, codec, gespeichert, summe)`` - ein Chunk (``gespeichert`` sind die Bytes, die ins Band kommen).

    Die Platte liest voraus, waehrend die Faeden verdichten. Die Chunks laufen dateiuebergreifend durch die Faeden (kleine Dateien
    halten nicht mehr alle bis auf einen auf Leerlauf); geliefert wird trotzdem Chunk fuer Chunk in Indexordnung, das Ergebnis
    haengt nicht von den Faeden ab. Wer den Erzeuger nicht bis zum Ende laeuft, ruft ``close()`` (Faeden, Lesevorlauf).
    """
    arbeiter = _arbeiterzahl(arbeiter)
    lokal = threading.local()                               # je Arbeitsfaden ein eigener Kompressor

    def verdichten(daten: bytes) -> tuple[int, bytes, int]:
        kompressor = getattr(lokal, "kompressor", None)
        if kompressor is None:
            kompressor = lokal.kompressor = _kompressor(stufe)
        codec, gespeichert = chunk_verdichten(daten, stufe, kompressor)
        return codec, gespeichert, _crc(daten)              # die Pruefsumme der Quelle merkt sich die Pruefung (kein zweites Lesen)

    def quellen_lesen() -> Iterator[tuple[int, list[bytes], bool]]:
        for nummer, (_h, _roh, rel, groesse) in enumerate(eintraege):
            erstes = True
            for chunks in bloecke_fuer(rel, groesse):
                yield nummer, chunks, erstes
                erstes = False
            if erstes:                                      # leere Datei: kein Stueck, aber der Eintrag zaehlt
                yield nummer, [], True

    def liefern(ausstehend: "deque", bis: int) -> Iterator[tuple]:
        while len(ausstehend) > bis:
            daten, zukunft = ausstehend.popleft()
            codec, gespeichert, summe = zukunft.result()
            yield ("chunk", len(daten), codec, gespeichert, summe)

    fenster = arbeiter * 4
    ausstehend: "deque[tuple[bytes, concurrent.futures.Future]]" = deque()
    with concurrent.futures.ThreadPoolExecutor(max_workers=arbeiter) as pool:
        vorlauf = _Vorlauf(quellen_lesen())
        try:
            for nummer, chunks, erstes in vorlauf:
                if abbruch():
                    raise ZstdPackFehler("ampr_pack.abgebrochen")
                if erstes:
                    yield ("datei", nummer)
                for daten in chunks:
                    ausstehend.append((daten, pool.submit(verdichten, daten)))
                    yield from liefern(ausstehend, fenster)
            yield from liefern(ausstehend, 0)
        finally:
            vorlauf.schliessen()


def _ordner_bloecke(wurzel: str) -> "Callable[[str, int], Iterator[list[bytes]]]":
    def fuer(rel: str, groesse: int) -> Iterator[list[bytes]]:
        voll = os.path.join(wurzel, *rel.split("/"))
        if os.path.getsize(voll) != groesse:
            raise ZstdPackFehler("%s hat sich waehrend des Packens veraendert" % rel)
        return _datei_bloecke(voll, groesse)
    return fuer


def _baum_bloecke(dateien: "dict[str, Any]") -> "Callable[[str, int], Iterator[list[bytes]]]":
    """Quellen aus einem Lesebaum (``spielbaum``). Dessen Stuecke haben beliebige Laengen; die Chunks liegen aber an festen
    Stellen der Datei, deshalb werden sie hier zu Bloecken von ``LESE_BLOCK`` Bytes zusammengesetzt."""
    def fuer(rel: str, groesse: int) -> Iterator[list[bytes]]:
        datei = dateien.get(rel)
        if datei is None:
            raise ZstdPackFehler("%s fehlt in der Quelle" % rel)
        if datei.groesse != groesse:
            raise ZstdPackFehler("%s hat sich waehrend des Packens veraendert" % rel)
        return _stuecke_zu_bloecken(datei)
    return fuer


def _stuecke_zu_bloecken(datei: Any) -> Iterator[list[bytes]]:
    def zerlegen(block: "bytes | bytearray") -> list[bytes]:
        return [bytes(block[i:i + CHUNK_SIZE]) for i in range(0, len(block), CHUNK_SIZE)]

    puffer = bytearray()
    try:
        for stueck in datei.lesen(LESE_BLOCK):
            puffer += stueck
            while len(puffer) >= LESE_BLOCK:
                block = puffer[:LESE_BLOCK]
                del puffer[:LESE_BLOCK]
                yield zerlegen(block)
        if puffer:
            yield zerlegen(puffer)
    except BaumFehler as exc:
        raise ZstdPackFehler(str(exc)) from exc


@dataclass
class Messung:
    """Das Ergebnis des Messdurchgangs: alles, was der Schreibdurchgang vorab braucht, ohne dass ein Byte gespeichert wurde."""

    archiv_id: bytes
    stufe: int
    #: ``(Pfad, Groesse)`` der gepackten Dateien in der Reihenfolge des Index.
    eintraege: list[tuple[str, int]]
    chunkwoerter: list[int]
    summen: "array[int]"
    #: Groesse jedes Bandes mit Kopf.
    baender: list[int]
    #: Der ganze Inhalt von ``ampr_zstd.index``.
    index: bytes
    ergebnis: Ergebnis

    def dateien(self) -> list[tuple[str, int]]:
        """``(Name, Groesse)`` der Dateien, die der Schreibdurchgang liefert: erst die Baender, dann der Index."""
        return [(bandname(n), g) for n, g in enumerate(self.baender)] + [(INDEX_NAME, len(self.index))]

    @property
    def gesamtgroesse(self) -> int:
        return sum(g for _n, g in self.dateien())


def _pruefen_vorab(auswahl: Auswahl) -> None:
    if _zstd is None:
        raise ZstdPackFehler("ampr_zstd.bibliothek_fehlt")
    if not auswahl.gepackt:
        raise ZstdPackFehler("ampr_zstd.nichts_zu_packen")


def messen(baum: Any, auswahl: Auswahl, *, stufe: int = STUFE_VORGABE, arbeiter: int = 0, archiv_id: "bytes | None" = None,
           abbruch: Callable[[], bool] = lambda: False, fortschritt: "Callable[[float], None] | None" = None) -> Messung:
    """Messdurchgang: verdichtet alles aus dem Lesebaum und behaelt nur, was der Schreibdurchgang vorab braucht.

    Nichts wird geschrieben. Der Durchgang kostet das Lesen der Quelle und das Verdichten, aber keinen Platz - das ist der Preis
    dafuer, dass kein Zwischenordner gebraucht wird: Die Groesse eines Bandes steht in seinem Kopf, und der Kopf liegt vor den
    Daten. ``archiv_id`` ohne Angabe ist zufaellig; :func:`archiv_id_ableiten` liefert eine, die ein Abbild reproduzierbar macht.
    """
    _pruefen_vorab(auswahl)
    stufe = stufe_lesen(stufe)
    plan = _Plan(auswahl, stufe, archiv_id or uuid.uuid4().bytes)
    folge = _chunk_folge(plan.eintraege, _baum_bloecke(baum.suchen()), stufe, arbeiter, abbruch)
    try:
        for art, *rest in folge:
            if art == "datei":
                plan.datei_beginnt(rest[0])
                continue
            rohlaenge, codec, gespeichert, summe = rest
            plan.chunk(rohlaenge, codec, len(gespeichert), summe)
            if fortschritt is not None:
                fortschritt(plan.anteil())
    finally:
        folge.close()
    plan.ende()
    return Messung(archiv_id=plan.archiv, stufe=stufe, eintraege=[(e[2], e[3]) for e in plan.eintraege],
                   chunkwoerter=plan.chunkwoerter, summen=plan.summen, baender=plan.baeume, index=plan.index(),
                   ergebnis=plan.ergebnis)


def stichprobe_chunks(messung: "Messung", startwert: int) -> "tuple[frozenset[int], int]":
    """Welche Chunks die Fast-Pruefung im Strom entpackt: ``(Chunknummern, Bytes)``; die Regeln wie bei :func:`stichprobe_planen`.

    Dateien bis ``GANZ_BIS_STUECKE`` Stuecke (zu ``LESE_BLOCK`` Bytes) ganz, von groesseren das erste und das letzte Stueck und
    dazu zufaellige - zusammen hoechstens ``STICHPROBE_MAX`` Bytes und hoechstens ``STICHPROBE_ANTEIL`` des Rests (mindestens
    ein Stueck). Gleicher Startwert, gleiche Auswahl. Die Nummern zaehlen ueber alle Dateien der Messung in ihrer Reihenfolge.
    """
    je_stueck = max(1, LESE_BLOCK // CHUNK_SIZE)
    gewaehlt: set[int] = set()
    gesamt = rest = 0
    kandidaten: "list[tuple[int, int, int, int]]" = []          # (erster Chunk der Datei, Chunks der Datei, Stueck, Bytes)
    erster = 0
    for _pfad, groesse in messung.eintraege:
        n = -(-groesse // CHUNK_SIZE)
        if n <= 0:
            continue
        stuecke = -(-n // je_stueck)

        def stueck_bytes(s: int, groesse: int = groesse) -> int:
            return max(0, min(LESE_BLOCK, groesse - s * LESE_BLOCK))

        def stueck_chunks(s: int, erster: int = erster, n: int = n) -> "range":
            return range(erster + s * je_stueck, erster + min(n, (s + 1) * je_stueck))

        if stuecke <= GANZ_BIS_STUECKE:
            gewaehlt.update(range(erster, erster + n))
            gesamt += groesse
        else:
            for s in {0, stuecke - 1}:
                gewaehlt.update(stueck_chunks(s))
                gesamt += stueck_bytes(s)
            for s in range(1, stuecke - 1):
                kandidaten.append((erster, n, s, stueck_bytes(s)))
                rest += stueck_bytes(s)
        erster += n
    if kandidaten:
        zufall = random.Random(startwert)
        zufall.shuffle(kandidaten)
        budget = max(LESE_BLOCK, min(STICHPROBE_MAX, int(rest * STICHPROBE_ANTEIL)))
        for erster_chunk, n, s, b in kandidaten:
            if budget < b:
                break
            gewaehlt.update(range(erster_chunk + s * je_stueck, erster_chunk + min(n, (s + 1) * je_stueck)))
            budget -= b
            gesamt += b
    return frozenset(gewaehlt), gesamt


def strom(baum: Any, auswahl: Auswahl, messung: Messung, *, arbeiter: int = 0, abbruch: Callable[[], bool] = lambda: False,
          fortschritt: "Callable[[float], None] | None" = None,
          pruefen: "bool | frozenset[int] | set[int] | None" = None) -> Iterator[tuple[str, bytes]]:
    """Schreibdurchgang: verdichtet noch einmal und liefert ``(Dateiname, Bytes)`` in der Reihenfolge von ``messung.dateien()``.

    Aufeinanderfolgende Stuecke mit demselben Namen gehoeren zu einer Datei; deren Laenge ist die in ``messung.dateien()``.
    Jeder Chunk wird gegen die Messung verglichen (Stelle im Band und Pruefsumme der Quelle): Hat sich die Quelle zwischen den
    Durchgaengen geaendert oder verdichtet die Bibliothek nicht reproduzierbar, bricht der Durchgang mit einem Fehler ab, ehe
    ein falsches Pack abgeliefert ist. Der Aufrufer ruft bei vorzeitigem Ende ``close()`` auf dem Erzeuger.

    ``pruefen`` (wie beim Pack im Ordner ``pruefen``): ``True`` entpackt **jeden** Chunk, den der Durchgang abliefert, und
    vergleicht ihn mit der Pruefsumme der Quelle; eine Menge von Chunknummern (:func:`stichprobe_chunks`) nur diese; ``None``
    nichts. So ist das Pack auf dem Weg ins Abbild nachweislich entpackbar und gleich der Quelle - ein Fehler der Verdichtung faellt
    auf, ehe das Abbild fertig ist.
    """
    _pruefen_vorab(auswahl)
    plan = _Plan(auswahl, messung.stufe, messung.archiv_id)
    if [(e[2], e[3]) for e in plan.eintraege] != messung.eintraege:
        raise ZstdPackFehler("Dateiliste weicht von der Messung ab")
    anzahl = len(messung.baender)

    def kopf(nummer: int) -> bytes:
        return _bandkopf(nummer, anzahl, messung.archiv_id, messung.baender[nummer])

    folge = _chunk_folge(plan.eintraege, _baum_bloecke(baum.suchen()), messung.stufe, arbeiter, abbruch)
    try:
        yield bandname(0), kopf(0)
        nr = 0
        for art, *rest in folge:
            if art == "datei":
                plan.datei_beginnt(rest[0])
                continue
            rohlaenge, codec, gespeichert, summe = rest
            neu = plan.chunk(rohlaenge, codec, len(gespeichert), summe)
            if (nr >= len(messung.chunkwoerter) or plan.chunkwoerter[-1] != messung.chunkwoerter[nr]
                    or summe != messung.summen[nr]):
                raise ZstdPackFehler("Schreibdurchgang weicht vom Messdurchgang ab (Chunk %d): die Quelle hat sich "
                                     "geaendert, oder die Verdichtung ist nicht reproduzierbar" % nr)
            if pruefen is True or (pruefen and nr in pruefen):
                if codec == CODEC_ZSTD:
                    rahmen_pruefen(gespeichert, rohlaenge)
                if _crc(chunk_entpacken(codec, gespeichert, rohlaenge)) != summe:
                    raise ZstdPackFehler("ampr_zstd.inhalt_anders: Chunk %d" % nr)
            nr += 1
            if neu:
                yield bandname(plan.band), kopf(plan.band)
            yield bandname(plan.band), gespeichert
            if fortschritt is not None:
                fortschritt(plan.anteil())
    finally:
        folge.close()
    plan.ende()
    if nr != len(messung.chunkwoerter) or plan.baeume != messung.baender or plan.index() != messung.index:
        raise ZstdPackFehler("Schreibdurchgang weicht vom Messdurchgang ab (Baender oder Index)")
    yield INDEX_NAME, messung.index


def strom_in_ordner(baum: Any, auswahl: Auswahl, messung: Messung, ausgabe: str, *, arbeiter: int = 0,
                    abbruch: Callable[[], bool] = lambda: False,
                    fortschritt: "Callable[[float], None] | None" = None) -> None:
    """Schreibt den Strom in Dateien unter ``ausgabe`` (ein leerer, neuer Ordner) - fuer Pruefungen und als Rueckfall."""
    os.makedirs(ausgabe, exist_ok=True)
    for name in os.listdir(ausgabe):
        if ist_packname(name):
            raise ZstdPackFehler("ampr_zstd.ausgabe_belegt")
    erzeuger = strom(baum, auswahl, messung, arbeiter=arbeiter, abbruch=abbruch, fortschritt=fortschritt)
    fh = None
    aktuell = ""
    try:
        for name, daten in erzeuger:
            if name != aktuell:
                if fh is not None:
                    fh.close()
                fh = open(os.path.join(ausgabe, name), "wb", buffering=4 << 20)
                aktuell = name
            fh.write(daten)
    finally:
        erzeuger.close()
        if fh is not None:
            fh.close()


def packen(app0: str, ausgabe: str, auswahl: Auswahl, *, stufe: int = STUFE_VORGABE, arbeiter: int = 0,
           melden: Melder = _stumm, abbruch: Callable[[], bool] = lambda: False,
           fortschritt: "Callable[[float], None] | None" = None, archiv_id: "bytes | None" = None) -> Ergebnis:
    """Schreibt Baender und Index nach ``ausgabe`` (ein leerer, neuer Ordner).

    Die Dateien des Spielordners werden nur gelesen. Bei einem Fehler oder Abbruch bleibt in ``ausgabe`` ein
    Rest zurueck, den der Aufrufer wegraeumt.
    """
    if _zstd is None:
        raise ZstdPackFehler("ampr_zstd.bibliothek_fehlt")
    stufe = stufe_lesen(stufe)
    wurzel = os.path.abspath(app0)
    if not auswahl.gepackt:
        raise ZstdPackFehler("ampr_zstd.nichts_zu_packen")
    os.makedirs(ausgabe, exist_ok=True)
    for name in os.listdir(ausgabe):
        if ist_packname(name):
            raise ZstdPackFehler("ampr_zstd.ausgabe_belegt")

    plan = _Plan(auswahl, stufe, archiv_id or uuid.uuid4().bytes)
    ergebnis = plan.ergebnis
    fh: Any = None

    def band_oeffnen() -> None:
        nonlocal fh
        fh = open(os.path.join(ausgabe, bandname(plan.band)), "wb", buffering=4 << 20)
        fh.write(b"\0" * VOLUME_HEADER_SIZE)

    folge = _chunk_folge(plan.eintraege, _ordner_bloecke(wurzel), stufe, arbeiter, abbruch)
    try:
        band_oeffnen()
        for art, *rest in folge:
            if art == "datei":
                plan.datei_beginnt(rest[0])
                continue
            rohlaenge, codec, gespeichert, summe = rest
            if plan.chunk(rohlaenge, codec, len(gespeichert), summe):
                fh.flush()
                fh.close()
                band_oeffnen()
            fh.write(gespeichert)
            if fortschritt is not None:
                fortschritt(plan.anteil())
        fh.flush()
        fh.close()
        fh = None
    finally:
        folge.close()
        if fh is not None:
            fh.close()
    plan.ende()

    # Kopfzeilen der Baender (zuletzt, wenn die Groessen feststehen)
    for nummer in range(len(plan.baeume)):
        with open(os.path.join(ausgabe, bandname(nummer)), "r+b") as band_fh:
            band_fh.write(plan.bandkopf(nummer))

    with open(os.path.join(ausgabe, INDEX_NAME), "wb") as index_fh:
        index_fh.write(plan.index())
    melden("ampr_zstd: %d Dateien, %d Chunks (%d zstd, %d roh), %d Band/Baender, Stufe %d" % (
        ergebnis.dateien, ergebnis.chunks, ergebnis.zstd_chunks, ergebnis.roh_chunks, len(plan.baeume), stufe))
    return ergebnis


# ---------------------------------------------------------------------------
# Lesen und Pruefen
# ---------------------------------------------------------------------------
@dataclass
class Datei:
    pfad: str
    hash: int
    groesse: int
    erster_chunk: int
    chunk_zahl: int


@dataclass
class Index:
    """Der geprueft gelesene Index."""

    archiv_id: bytes
    stufe: int
    dateien: list[Datei]
    chunks: list[tuple[int, int, int, int]]   # (Offset, Band, gespeichert, Codec)
    baender: list[int]
    logische_bytes: int


def index_lesen(daten: bytes) -> Index:
    """Liest und prueft einen Index mit denselben Regeln wie der Leser von ampr-emu-ng."""

    def fehler(text: str):
        raise ZstdPackFehler("ampr_zstd.index_ungueltig: %s" % text)

    if len(daten) < INDEX_HEADER_SIZE:
        fehler("zu kurz")
    h = daten[:INDEX_HEADER_SIZE]
    if h[:8] != INDEX_MAGIC:
        fehler("Kennung")
    version, kopfgroesse = struct.unpack_from("<II", h, 8)
    if version != FORMAT_VERSION or kopfgroesse != INDEX_HEADER_SIZE or h[16] != CHUNK_SHIFT:
        fehler("Version/Kopf/Chunkgroesse")
    stufe = h[17]
    if not STUFE_MIN <= stufe <= STUFE_MAX or struct.unpack_from("<H", h, 18)[0] != 0:
        fehler("Stufe/Reserve")
    if struct.unpack_from("<Q", h, 104)[0] != 0 or struct.unpack_from("<Q", h, 120)[0] != 0:
        fehler("Reserve")
    if _crc(h[:112] + b"\0" * 8 + h[120:]) != struct.unpack_from("<I", h, 116)[0]:
        raise ZstdPackFehler("ampr_zstd.index_pruefsumme")
    if _crc(daten[INDEX_HEADER_SIZE:]) != struct.unpack_from("<I", h, 112)[0]:
        raise ZstdPackFehler("ampr_zstd.index_pruefsumme")
    bandzahl = struct.unpack_from("<I", h, 20)[0]
    archiv = bytes(h[24:40])
    (dateizahl, chunkzahl, files_off, chunks_off, volumes_off, strings_off, strings_len,
     logisch) = struct.unpack_from("<QQQQQQQQ", h, 40)
    if bandzahl > MAX_VOLUMES or chunkzahl > 0xFFFFFFFF:
        fehler("Anzahlen")
    if (files_off != INDEX_HEADER_SIZE or files_off + dateizahl * FILE_RECORD_SIZE != chunks_off
            or chunks_off + chunkzahl * CHUNK_RECORD_SIZE != volumes_off
            or volumes_off + bandzahl * VOLUME_RECORD_SIZE != strings_off
            or strings_off + strings_len != len(daten) or (chunkzahl == 0) != (bandzahl == 0)):
        fehler("Tabellen")
    strings = daten[strings_off:]
    chunks: list[tuple[int, int, int, int]] = []
    for i in range(chunkzahl):
        wort = struct.unpack_from("<Q", daten, chunks_off + i * 8)[0]
        if wort >> 62 > 1:
            fehler("Codec")
        offset = wort & 0xFFFFFFFF
        band = (wort >> 32) & 0xFFF
        gespeichert = ((wort >> 44) & 0x3FFFF) + 1
        if offset < VOLUME_HEADER_SIZE or offset + gespeichert > VOLUME_LIMIT:
            fehler("Chunkbeschreibung")
        chunks.append((offset, band, gespeichert, wort >> 62))
    baender = [struct.unpack_from("<Q", daten, volumes_off + i * 8)[0] for i in range(bandzahl)]
    dateien: list[Datei] = []
    naechster_chunk = naechster_string = gesamt = 0
    vorher: "tuple[int, bytes] | None" = None
    band_jetzt, naechster_offset = 0, VOLUME_HEADER_SIZE
    for i in range(dateizahl):
        satz = daten[files_off + i * FILE_RECORD_SIZE: files_off + (i + 1) * FILE_RECORD_SIZE]
        hash_, groesse, erster, pfad_off, pfad_len, flags, reserve = struct.unpack("<QQIIHHI", satz)
        roh = bytes(strings[pfad_off:pfad_off + pfad_len])
        try:
            pfad = roh.decode("utf-8")
        except UnicodeDecodeError:
            fehler("Pfad nicht UTF-8")
        zahl = -(-groesse // CHUNK_SIZE)
        if (pfad_off != naechster_string or reserve != 0 or flags & ~1 or not pfad_gueltig(pfad)
                or hash_ != pfadhash(roh) or erster != naechster_chunk
                or (vorher is not None and vorher >= (hash_, roh))):
            fehler("Dateisatz %d" % i)
        naechster_string += pfad_len
        naechster_chunk += zahl
        gesamt += groesse
        vorher = (hash_, roh)
        for n in range(zahl):
            offset, band, gespeichert, codec = chunks[erster + n]
            entpackt = min(CHUNK_SIZE, groesse - n * CHUNK_SIZE)
            if (band >= bandzahl or (codec == CODEC_ROH and gespeichert != entpackt)
                    or (codec == CODEC_ZSTD and gespeichert >= entpackt) or (flags & 1 and codec != CODEC_ROH)):
                fehler("Chunk in Datei %d" % i)
            if band != band_jetzt:
                if band != band_jetzt + 1 or naechster_offset != baender[band_jetzt]:
                    fehler("Bandwechsel")
                band_jetzt, naechster_offset = band, VOLUME_HEADER_SIZE
            if offset != naechster_offset:
                fehler("Chunkoffset")
            naechster_offset += gespeichert
            if naechster_offset > baender[band]:
                fehler("Chunk ueber Bandende")
        dateien.append(Datei(pfad, hash_, groesse, erster, zahl))
    if naechster_string != len(strings) or naechster_chunk != chunkzahl or gesamt != logisch:
        fehler("Summen")
    for g in baender:
        if not VOLUME_HEADER_SIZE <= g <= VOLUME_LIMIT:
            fehler("Bandgroesse")
    if bandzahl and (band_jetzt + 1 != bandzahl or naechster_offset != baender[band_jetzt]):
        fehler("letztes Band")
    return Index(archiv, stufe, dateien, chunks, baender, logisch)


def bandkopf_pruefen(kopf: bytes, nummer: int, index: Index) -> None:
    """Prueft die 64 Bytes eines Bands gegen den Index."""
    if len(kopf) < VOLUME_HEADER_SIZE or kopf[:8] != VOLUME_MAGIC:
        raise ZstdPackFehler("ampr_zstd.band_ungueltig")
    version, groesse, band_id, zahl = struct.unpack_from("<IIII", kopf, 8)
    nutzlast = struct.unpack_from("<Q", kopf, 40)[0]
    if (version != FORMAT_VERSION or groesse != VOLUME_HEADER_SIZE or band_id != nummer
            or zahl != len(index.baender) or bytes(kopf[24:40]) != index.archiv_id
            or nutzlast != index.baender[nummer] - VOLUME_HEADER_SIZE or any(kopf[48:60])):
        raise ZstdPackFehler("ampr_zstd.band_ungueltig")
    if _crc(bytes(kopf[:60]) + b"\0\0\0\0") != struct.unpack_from("<I", kopf, 60)[0]:
        raise ZstdPackFehler("ampr_zstd.band_pruefsumme")


def index_laden(ordner: str) -> Index:
    pfad = os.path.join(ordner, INDEX_NAME)
    try:
        with open(pfad, "rb") as fh:
            return index_lesen(fh.read())
    except OSError as exc:
        raise ZstdPackFehler("ampr_zstd.index_fehlt: %s" % exc) from exc


def _datei_chunks(index: Index, datei: Datei) -> Iterator[tuple[int, tuple[int, int, int, int]]]:
    for n in range(datei.chunk_zahl):
        yield n, index.chunks[datei.erster_chunk + n]


#: Fast-Pruefung wie bei Dump Forge: Dateien bis ``GANZ_BIS_STUECKE`` Stuecke werden ganz geprueft, von groesseren das
#: erste und das letzte Stueck und dazu zufaellige Stuecke - zusammen hoechstens ``STICHPROBE_MAX`` Bytes und hoechstens
#: ``STICHPROBE_ANTEIL`` des Rests (mindestens eines).
GANZ_BIS_STUECKE = 2
STICHPROBE_MAX = 1 << 30
STICHPROBE_ANTEIL = 0.01


def _stueck_bytes(datei: "Datei", stueck: int) -> int:
    """Wie viele Bytes der Datei im ``stueck``-ten Stueck (zu ``LESE_BLOCK`` Bytes) liegen."""
    return max(0, min(LESE_BLOCK, datei.groesse - stueck * LESE_BLOCK))


def stichprobe_planen(index: "Index", startwert: int) -> "tuple[dict[int, frozenset[int] | None], int]":
    """Welche Stuecke die Fast-Pruefung liest: ``({Dateinummer: Stuecke oder None fuer ganz}, Bytes)``.

    Gleiche Pruefstuecke gleich Startwert gleich Auswahl, damit sich ein Lauf wiederholen laesst. Leere Dateien fehlen im
    Plan (es gibt nichts zu lesen).
    """
    je_stueck = max(1, LESE_BLOCK // CHUNK_SIZE)
    ganz: list[int] = []                         # Dateien, die ganz geprueft werden
    teile: dict[int, set[int]] = {}              # grosse Dateien: die gewaehlten Stuecke
    gesamt = 0
    kandidaten: "list[tuple[int, int]]" = []
    rest = 0
    for nummer, datei in enumerate(index.dateien):
        if datei.groesse <= 0 or datei.chunk_zahl <= 0:
            continue
        stuecke = -(-datei.chunk_zahl // je_stueck)
        if stuecke <= GANZ_BIS_STUECKE:
            ganz.append(nummer)
            gesamt += datei.groesse
            continue
        feste = {0, stuecke - 1}
        teile[nummer] = set(feste)
        gesamt += sum(_stueck_bytes(datei, s) for s in feste)
        for s in range(1, stuecke - 1):
            kandidaten.append((nummer, s))
            rest += _stueck_bytes(datei, s)
    if kandidaten:
        zufall = random.Random(startwert)
        zufall.shuffle(kandidaten)
        budget = max(LESE_BLOCK, min(STICHPROBE_MAX, int(rest * STICHPROBE_ANTEIL)))
        for nummer, s in kandidaten:
            b = _stueck_bytes(index.dateien[nummer], s)
            if budget < b:
                break
            teile[nummer].add(s)
            budget -= b
            gesamt += b
    plan: "dict[int, frozenset[int] | None]" = dict.fromkeys(ganz)
    plan.update({n: frozenset(s) for n, s in teile.items()})
    return plan, gesamt


def _pruef_stuecke(index: Index, handles: dict[int, Any], app0: str,
                   plan: "dict[int, frozenset[int] | None] | None" = None,
                   quelle_lesen: bool = True
                   ) -> Iterator[tuple[Datei, int, list[tuple[int, bytes]], "bytes | None"]]:
    """Lesevorlauf der Pruefung: je Stueck ``(Datei, Nummer des ersten Chunks, [(Codec, gespeicherte Bytes)], Quelle)``.

    Das Band wird in grossen Bloecken gelesen (siehe :class:`_BandPuffer`), die Quelldatei je Stueck mit einem Aufruf -
    der Kopf der Platte wechselt so alle ``LESE_BLOCK`` Bytes zwischen Pack und Quelle statt nach jedem Chunk.

    Mit ``plan`` (:func:`stichprobe_planen`) kommen nur die geplanten Stuecke; alles andere wird weder aus dem Band
    noch aus der Quelle gelesen. Ohne ``quelle_lesen`` wird die Quelldatei nur angesehen (Groesse), nie geoeffnet.
    """
    puffer = {nummer: _BandPuffer(fh) for nummer, fh in handles.items()}
    je_stueck = max(1, LESE_BLOCK // CHUNK_SIZE)
    for dateinummer, datei in enumerate(index.dateien):
        gewaehlt = None
        if plan is not None:
            if dateinummer not in plan:
                continue
            gewaehlt = plan[dateinummer]
        quelle = None
        if app0:
            voll = os.path.join(os.path.abspath(app0), *datei.pfad.split("/"))
            try:
                if os.path.getsize(voll) != datei.groesse:
                    raise ZstdPackFehler("ampr_zstd.quelle_anders: %s" % datei.pfad)
                if quelle_lesen:
                    quelle = open(voll, "rb")
            except OSError as exc:
                raise ZstdPackFehler("ampr_zstd.quelle_fehlt: %s" % datei.pfad) from exc
        try:
            n = 0
            while n < datei.chunk_zahl:
                zahl = min(je_stueck, datei.chunk_zahl - n)
                if gewaehlt is not None and (n // je_stueck) not in gewaehlt:
                    n += zahl                         # nicht in der Stichprobe: weder Band noch Quelle lesen
                    continue
                if quelle is not None:
                    quelle.seek(n * CHUNK_SIZE)       # nach uebersprungenen Stuecken wieder an die richtige Stelle
                stuecke: list[tuple[int, bytes]] = []
                for k in range(zahl):
                    offset, band, gespeichert, codec = index.chunks[datei.erster_chunk + n + k]
                    gelesen = puffer[band].lesen(offset, gespeichert)
                    if len(gelesen) != gespeichert:
                        raise ZstdPackFehler("ampr_zstd.band_kurz: %s" % datei.pfad)
                    stuecke.append((codec, gelesen))
                roh = None
                if quelle is not None:
                    roh = quelle.read(min(zahl * CHUNK_SIZE, datei.groesse - n * CHUNK_SIZE))
                yield datei, n, stuecke, roh
                n += zahl
        finally:
            if quelle is not None:
                quelle.close()


def pruefen(ordner_packs: str, app0: str = "", *, melden: Melder = _stumm,
            abbruch: Callable[[], bool] = lambda: False,
            fortschritt: "Callable[[float], None] | None" = None,
            stichprobe: bool = False, startwert: "int | None" = None,
            bericht: "dict[str, Any] | None" = None,
            summen: "Sequence[int] | None" = None) -> Index:
    """Prueft Index und Baender und - mit ``app0`` - jeden Chunk **Byte fuer Byte** gegen die Quelldateien.

    Ohne ``app0`` wird jeder Chunk nur entpackt (Frame-Pruefsumme, Laenge). Die Rueckgabe ist der Index.

    Mit ``stichprobe`` (Fast-Pruefung wie bei Dump Forge) werden Index, Kopf jedes Bandes und die Dateigroessen wie
    sonst vollstaendig geprueft, vom Inhalt aber nur die Stuecke aus :func:`stichprobe_planen` entpackt und verglichen.
    ``startwert`` legt die Auswahl fest (ohne Angabe zufaellig). ``bericht`` bekommt ``modus`` ("voll" oder
    "stichprobe"), ``geprueft`` und ``gesamt`` (Bytes), ``startwert`` und ``vergleich`` ("pruefsummen" oder "quelle").

    Mit ``summen`` (``Ergebnis.pruefsummen`` des Packens, ein CRC-32 je Chunk) wird die Quelle **nicht noch einmal gelesen**:
    Jeder entpackte Chunk wird gegen die Summe verglichen, die beim Packen aus den Quellbytes berechnet wurde (Dump Forge
    macht es mit BLAKE3 ebenso). Das erkennt ein verdorbenes Band und einen Fehler des Packers; eine Quelle, die sich
    seit dem Packen veraendert hat, erkennt nur die Groessenpruefung. Passt die Zahl der Summen nicht zum Index, gilt der
    Vergleich mit der Quelle wie ohne ``summen``.

    Gelesen wird in grossen Bloecken und in einem eigenen Faden (Lesevorlauf), damit die Platte nicht je Chunk zwischen
    Pack und Quelle springt und waehrend des Entpackens nicht stillsteht.
    """
    index = index_laden(ordner_packs)
    handles: dict[int, Any] = {}
    if summen is not None and len(summen) != len(index.chunks):
        summen = None                                   # gehoeren nicht zu diesem Index: wie bisher gegen die Quelle
    plan = None
    if stichprobe:
        if startwert is None:
            startwert = random.SystemRandom().getrandbits(32)
        plan, geplant = stichprobe_planen(index, startwert)
        gesamt = max(1, geplant)
    else:
        gesamt = max(1, index.logische_bytes)
    erledigt = 0
    try:
        for nummer in range(len(index.baender)):
            pfad = os.path.join(ordner_packs, bandname(nummer))
            try:
                if os.path.getsize(pfad) != index.baender[nummer]:
                    raise ZstdPackFehler("ampr_zstd.band_groesse: %s" % bandname(nummer))
                handles[nummer] = open(pfad, "rb")
                bandkopf_pruefen(handles[nummer].read(VOLUME_HEADER_SIZE), nummer, index)
            except OSError as exc:
                raise ZstdPackFehler("ampr_zstd.band_fehlt: %s (%s)" % (bandname(nummer), exc)) from exc
        vorlauf = _Vorlauf(_pruef_stuecke(index, handles, app0, plan, quelle_lesen=summen is None))
        try:
            for datei, erster, stuecke, roh in vorlauf:
                if abbruch():
                    raise ZstdPackFehler("ampr_pack.abgebrochen")
                position = 0
                for k, (codec, gelesen) in enumerate(stuecke):
                    erwartet = min(CHUNK_SIZE, datei.groesse - (erster + k) * CHUNK_SIZE)
                    if codec == CODEC_ZSTD:
                        rahmen_pruefen(gelesen, erwartet)
                    entpackt = chunk_entpacken(codec, gelesen, erwartet)
                    if roh is not None and roh[position:position + erwartet] != entpackt:
                        raise ZstdPackFehler("ampr_zstd.inhalt_anders: %s" % datei.pfad)
                    if summen is not None and app0 and _crc(entpackt) != summen[datei.erster_chunk + erster + k]:
                        raise ZstdPackFehler("ampr_zstd.inhalt_anders: %s" % datei.pfad)
                    position += erwartet
                    erledigt += erwartet
                    if fortschritt is not None:
                        fortschritt(min(1.0, erledigt / gesamt))
        finally:
            vorlauf.schliessen()
    finally:
        for fh in handles.values():
            fh.close()
    if bericht is not None:
        bericht.update(modus="stichprobe" if stichprobe else "voll", geprueft=erledigt,
                       gesamt=index.logische_bytes, startwert=startwert,
                       vergleich="pruefsummen" if (summen is not None and app0) else ("quelle" if app0 else "keiner"))
    melden("ampr_zstd: geprueft, %d Dateien, %d Chunks" % (len(index.dateien), len(index.chunks)))
    return index


# ---------------------------------------------------------------------------
# Spielordner: erkennen, uebernehmen, Originale entfernen, entpacken
# ---------------------------------------------------------------------------
def ist_gepackt(ordner: str) -> bool:
    """Ob im Spielordner ein zstd-Pack liegt (Index mit der Kennung ``AMPRZPK1``)."""
    pfad = os.path.join(ordner, INDEX_NAME)
    try:
        with open(pfad, "rb") as fh:
            return fh.read(8) == INDEX_MAGIC
    except OSError:
        return False


def uebernehmen(ausgabe: str, app0: str, index: Index, *, melden: Melder = _stumm,
                abbruch: Callable[[], bool] = lambda: False) -> None:
    """Legt Baender und Index in den Spielordner (zuerst die Baender, der Index zuletzt, jedes per Verschieben/Kopie)."""
    namen = [bandname(i) for i in range(len(index.baender))] + [INDEX_NAME]
    # Ein frueherer Satz verliert zuerst seinen Index: bricht die Uebernahme mitten in den Baendern ab, liegt dann
    # kein Mischsatz aus alten und neuen Baendern mit gueltigem Index da, sondern ein Ordner, der nicht als gepackt
    # gilt (die Originale sind zu diesem Zeitpunkt noch da, sie fallen erst nach der Pruefung weg).
    alter_index = os.path.join(app0, INDEX_NAME)
    if os.path.exists(alter_index):
        os.remove(alter_index)
    for name in namen:
        if abbruch():
            raise ZstdPackFehler("ampr_pack.abgebrochen")
        quelle = os.path.join(ausgabe, name)
        ziel = os.path.join(app0, name)
        erwartet = os.path.getsize(quelle)
        try:
            os.replace(quelle, ziel)
        except OSError:
            import shutil
            shutil.copy2(quelle, ziel)
            os.remove(quelle)
        if os.path.getsize(ziel) != erwartet:
            raise ZstdPackFehler("ampr_zstd.uebernahme: %s" % name)
    melden("ampr_zstd: %d Datei(en) im Spielordner" % len(namen))


def originale_entfernen(app0: str, index: Index, *, melden: Melder = _stumm,
                        abbruch: Callable[[], bool] = lambda: False) -> dict[str, int]:
    """Loescht die gepackten Originale und leer gewordene Ordner. Nur nach erfolgreicher Pruefung aufrufen."""
    wurzel = os.path.abspath(app0)
    entfernt = bytes_ = 0
    ordner: set[str] = set()
    for datei in index.dateien:
        if abbruch():
            raise ZstdPackFehler("ampr_pack.abgebrochen")
        if bleibt_lose(datei.pfad):
            raise ZstdPackFehler("ampr_zstd.system_im_pack: %s" % datei.pfad)
        voll = ziel_pfad(wurzel, datei.pfad)
        try:
            os.remove(voll)
        except FileNotFoundError:
            continue
        entfernt += 1
        bytes_ += datei.groesse
        ordner.add(os.path.dirname(voll))
    leer = 0
    for o in sorted(ordner, key=len, reverse=True):
        aktuell = o
        while aktuell and os.path.abspath(aktuell) != wurzel and os.path.isdir(aktuell):
            try:
                os.rmdir(aktuell)
            except OSError:
                break
            leer += 1
            aktuell = os.path.dirname(aktuell)
    melden("ampr_zstd: %d Originale entfernt, %d leere Ordner" % (entfernt, leer))
    return {"files": entfernt, "bytes": bytes_, "directories": leer}


def entpacken(ordner: str, ziel: str, *, melden: Melder = _stumm,
              abbruch: Callable[[], bool] = lambda: False,
              fortschritt: "Callable[[float], None] | None" = None) -> int:
    """Schreibt die gepackten Dateien in ``ziel`` (der Spielordner selbst oder eine Kopie) zurueck.

    Eine vorhandene Datei gleichen Namens wird durch den entpackten Inhalt ersetzt, und zwar atomar: erst entsteht
    ``<Datei>.zstd-teil``, dann ``os.replace``. Bricht ein Lauf ab, bleibt das Original unveraendert und die
    halbe ``.zstd-teil`` wird entfernt. Die Packdateien selbst werden nicht entfernt (das tut der Aufrufer nach Erfolg).
    """
    index = index_laden(ordner)
    gesamt = max(1, index.logische_bytes)
    erledigt = 0
    handles: dict[int, Any] = {}
    anzahl = 0
    try:
        for nummer in range(len(index.baender)):
            handles[nummer] = open(os.path.join(ordner, bandname(nummer)), "rb")
            bandkopf_pruefen(handles[nummer].read(VOLUME_HEADER_SIZE), nummer, index)
        for datei in index.dateien:
            if abbruch():
                raise ZstdPackFehler("ampr_pack.abgebrochen")
            voll = ziel_pfad(os.path.abspath(ziel), datei.pfad)
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            teil = voll + ".zstd-teil"
            try:
                with open(teil, "wb") as aus:
                    for n, (offset, band, gespeichert, codec) in _datei_chunks(index, datei):
                        handles[band].seek(offset)
                        erwartet = min(CHUNK_SIZE, datei.groesse - n * CHUNK_SIZE)
                        aus.write(chunk_entpacken(codec, handles[band].read(gespeichert), erwartet))
                        erledigt += erwartet
                        if fortschritt is not None:
                            fortschritt(min(1.0, erledigt / gesamt))
                os.replace(teil, voll)
            except BaseException:
                # Abbruch, beschaedigter Block, Platte voll: keine halbe Datei zuruecklassen.
                try:
                    os.remove(teil)
                except OSError:
                    pass
                raise
            anzahl += 1
    except OSError as exc:
        raise ZstdPackFehler("ampr_zstd.entpacken: %s" % exc) from exc
    finally:
        for fh in handles.values():
            fh.close()
    melden("ampr_zstd: %d Dateien entpackt" % anzahl)
    return anzahl


def packdateien_entfernen(ordner: str) -> int:
    """Loescht Index und Baender aus dem Spielordner (nach erfolgreichem Entpacken)."""
    anzahl = 0
    for name in os.listdir(ordner):
        if ist_packname(name):
            try:
                os.remove(os.path.join(ordner, name))
                anzahl += 1
            except OSError:
                pass
    return anzahl


# ---------------------------------------------------------------------------
# Fuer das Asset-Pack-Werkzeug (Pruefen / Entpacken eines gepackten Ordners)
# ---------------------------------------------------------------------------
def befund(ordner: str) -> dict[str, int]:
    """Zahlen zu einem gepackten Spielordner (Index wird geprueft gelesen, die Baender nicht entpackt)."""
    index = index_laden(ordner)
    fehlend = [bandname(i) for i in range(len(index.baender)) if not os.path.isfile(os.path.join(ordner, bandname(i)))]
    return {"dateien": len(index.dateien), "logisch": index.logische_bytes, "baender": len(index.baender),
            "band_bytes": sum(index.baender), "chunks": len(index.chunks), "stufe": index.stufe,
            "fehlende_baender": len(fehlend), "erste_fehlende": fehlend[0] if fehlend else ""}


def lose_bytes(ordner: str) -> int:
    """Gesamtgroesse der Dateien, die keine Packdateien sind (so viel wird bei einer Kopie zusaetzlich geschrieben)."""
    summe = 0
    wurzel = os.path.abspath(ordner)
    for pfad, _unter, dateien in os.walk(wurzel):
        for name in dateien:
            rel = os.path.relpath(os.path.join(pfad, name), wurzel).replace(os.sep, "/")
            if not ist_packname(rel):
                try:
                    summe += os.path.getsize(os.path.join(pfad, name))
                except OSError:
                    pass
    return summe


def platzbedarf(ordner: str, in_ordner: bool) -> int:
    """Wie viel Platz das Entpacken braucht: im Ordner die entpackte Groesse, in einem neuen Ordner dazu die losen Dateien."""
    index = index_laden(ordner)
    return index.logische_bytes + (0 if in_ordner else lose_bytes(ordner))


def entpacken_in_ordner(ordner: str, *, melden: Melder = _stumm, abbruch: Callable[[], bool] = lambda: False,
                        fortschritt: "Callable[[float], None] | None" = None) -> dict[str, int]:
    """Entpackt im Spielordner selbst und entfernt danach Index und Baender."""
    index = index_laden(ordner)
    anzahl = entpacken(ordner, ordner, melden=melden, abbruch=abbruch, fortschritt=fortschritt)
    entfernt = packdateien_entfernen(ordner)
    return {"files": anzahl, "bytes": index.logische_bytes, "entfernt": entfernt}


def entpacken_in_neuen_ordner(ordner: str, ziel: str, *, melden: Melder = _stumm,
                              abbruch: Callable[[], bool] = lambda: False,
                              fortschritt: "Callable[[float], None] | None" = None) -> dict[str, int]:
    """Legt eine entpackte Kopie des Spiels in ``ziel`` an (neu oder leer); die Packdateien werden nicht kopiert."""
    import shutil
    ziel = os.path.abspath(ziel)
    if os.path.exists(ziel) and (not os.path.isdir(ziel) or os.listdir(ziel)):
        raise ZstdPackFehler("ampr_zstd.ziel_belegt")
    if ziel == os.path.abspath(ordner) or ziel.startswith(os.path.abspath(ordner) + os.sep):
        raise ZstdPackFehler("ampr_zstd.ziel_im_quellordner")
    index = index_laden(ordner)
    os.makedirs(ziel, exist_ok=True)
    kopiert = 0
    wurzel = os.path.abspath(ordner)

    def _lesefehler(exc: OSError) -> None:
        # Ein nicht lesbarer Unterordner darf nicht still fehlen: sonst waere die "Kopie" unvollstaendig und trotzdem "fertig".
        raise ZstdPackFehler("ampr_zstd.entpacken: %s" % exc) from exc

    for pfad, unter, dateien in os.walk(wurzel, onerror=_lesefehler):
        unter.sort()
        for name in sorted(dateien):
            if abbruch():
                raise ZstdPackFehler("ampr_pack.abgebrochen")
            voll = os.path.join(pfad, name)
            rel = os.path.relpath(voll, wurzel).replace(os.sep, "/")
            if ist_packname(rel):
                continue
            ziel_datei = os.path.join(ziel, *rel.split("/"))
            os.makedirs(os.path.dirname(ziel_datei), exist_ok=True)
            shutil.copy2(voll, ziel_datei)
            kopiert += 1
    anzahl = entpacken(ordner, ziel, melden=melden, abbruch=abbruch, fortschritt=fortschritt)
    return {"files": anzahl, "bytes": index.logische_bytes, "kopiert": kopiert}
