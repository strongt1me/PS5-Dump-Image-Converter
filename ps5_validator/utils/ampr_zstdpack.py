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
``fakelib*`` und die eigenen Dateien der Laufzeit). Alles andere, was nicht leer ist, wird gepackt - die NG-Laufzeit
bedient ein vollstaendig gepacktes Spiel.
"""

from __future__ import annotations

import concurrent.futures
import os
import struct
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

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

    ``eboot.bin`` (jeder Ordner), ``.elf``/``.self``/``.prx``/``.sprx``, alles in einem Wurzelordner ``sce_sys``,
    ``sce_module`` oder ``fakelib*`` und die Dateien der Laufzeit; dazu die Packdateien selbst.
    """
    klein = rel.lower()
    name = klein.rsplit("/", 1)[-1]
    erster = klein.split("/", 1)[0]
    if name == "eboot.bin" or klein.endswith((".elf", ".self", ".prx", ".sprx")):
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
            groesse = os.path.getsize(voll)
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
    # Ein Dateipfad darf nicht der Ordner einer anderen sein - im Dateisystem ausgeschlossen, hier nur zur Sicherheit.
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
def _chunks_lesen(pfad: str, groesse: int) -> Iterator[bytes]:
    gelesen = 0
    with open(pfad, "rb") as fh:
        while gelesen < groesse:
            block = fh.read(min(CHUNK_SIZE, groesse - gelesen))
            if not block:
                raise ZstdPackFehler("%s ist kuerzer als gemeldet" % pfad)
            gelesen += len(block)
            yield block
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


def packen(app0: str, ausgabe: str, auswahl: Auswahl, *, stufe: int = STUFE_VORGABE, arbeiter: int = 0,
           melden: Melder = _stumm, abbruch: Callable[[], bool] = lambda: False,
           fortschritt: "Callable[[float], None] | None" = None) -> Ergebnis:
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

    eintraege = []
    for rel, groesse in auswahl.gepackt:
        roh = rel.encode("utf-8")
        eintraege.append((pfadhash(roh), roh, rel, groesse))
    eintraege.sort(key=lambda e: (e[0], e[1]))
    if any(a[0] == b[0] and a[1] == b[1] for a, b in zip(eintraege, eintraege[1:])):
        raise ZstdPackFehler("ampr_zstd.pfad_doppelt")

    archiv = uuid.uuid4().bytes
    arbeiter = arbeiter if arbeiter and arbeiter > 0 else (os.cpu_count() or 2)
    arbeiter = max(1, min(arbeiter, 32))
    gesamt = max(1, auswahl.gepackte_bytes)

    chunkwoerter: list[int] = []
    dateisaetze: list[bytes] = []
    strings = bytearray()
    baeume: list[int] = []   # Groesse je Band (mit Kopf)
    ergebnis = Ergebnis(stufe=stufe, archiv_id=archiv)

    # Je Arbeitsfaden ein eigener Kompressor (der Kontext darf nicht gleichzeitig benutzt werden).
    kompressoren = [_kompressor(stufe) for _ in range(arbeiter)]

    band = {"nummer": 0, "fh": None, "offset": VOLUME_HEADER_SIZE, "chunks": 0}

    def band_oeffnen() -> None:
        if band["nummer"] >= MAX_VOLUMES:
            raise ZstdPackFehler("ampr_zstd.zu_viele_baender")
        pfad = os.path.join(ausgabe, bandname(band["nummer"]))
        band["fh"] = open(pfad, "wb")
        band["fh"].write(b"\0" * VOLUME_HEADER_SIZE)
        band["offset"] = VOLUME_HEADER_SIZE
        band["chunks"] = 0
        ergebnis.baender.append(bandname(band["nummer"]))

    def band_schliessen() -> None:
        fh = band["fh"]
        if fh is None:
            return
        fh.flush()
        fh.close()
        baeume.append(band["offset"])
        band["fh"] = None

    erledigt = 0
    first_chunk = 0
    try:
        band_oeffnen()
        with concurrent.futures.ThreadPoolExecutor(max_workers=arbeiter) as pool:
            for _h, roh, rel, groesse in eintraege:
                if abbruch():
                    raise ZstdPackFehler("ampr_pack.abgebrochen")
                voll = os.path.join(wurzel, *rel.split("/"))
                if os.path.getsize(voll) != groesse:
                    raise ZstdPackFehler("%s hat sich waehrend des Packens veraendert" % rel)
                pfad_off = len(strings)
                strings += roh
                dateisaetze.append(struct.pack("<QQIIHHI", _h, groesse, first_chunk, pfad_off, len(roh), 0, 0))
                anzahl = -(-groesse // CHUNK_SIZE)
                first_chunk += anzahl
                quelle = _chunks_lesen(voll, groesse)
                while True:
                    paket = []
                    for _ in range(arbeiter):
                        try:
                            paket.append(next(quelle))
                        except StopIteration:
                            break
                    if not paket:
                        break
                    if abbruch():
                        raise ZstdPackFehler("ampr_pack.abgebrochen")
                    futures = [pool.submit(chunk_verdichten, daten, stufe, kompressoren[i])
                               for i, daten in enumerate(paket)]
                    for daten, zukunft in zip(paket, futures):
                        codec, gespeichert = zukunft.result()
                        if band["offset"] + len(gespeichert) > VOLUME_LIMIT:
                            band_schliessen()
                            band["nummer"] += 1
                            band_oeffnen()
                        chunkwoerter.append(_chunk_wort(band["offset"], band["nummer"], len(gespeichert), codec))
                        band["fh"].write(gespeichert)
                        band["offset"] += len(gespeichert)
                        band["chunks"] += 1
                        ergebnis.chunks += 1
                        ergebnis.gespeicherte_bytes += len(gespeichert)
                        if codec == CODEC_ZSTD:
                            ergebnis.zstd_chunks += 1
                        else:
                            ergebnis.roh_chunks += 1
                        erledigt += len(daten)
                        if fortschritt is not None:
                            fortschritt(min(1.0, erledigt / gesamt))
                ergebnis.dateien += 1
                ergebnis.logische_bytes += groesse
        band_schliessen()
    finally:
        if band["fh"] is not None:
            band["fh"].close()

    # Kopfzeilen der Baender (zuletzt, wenn die Groessen feststehen)
    anzahl_baender = len(baeume)
    for nummer, groesse in enumerate(baeume):
        with open(os.path.join(ausgabe, bandname(nummer)), "r+b") as fh:
            fh.write(_bandkopf(nummer, anzahl_baender, archiv, groesse))

    # Index
    dateien_tab = b"".join(dateisaetze)
    chunks_tab = b"".join(struct.pack("<Q", w) for w in chunkwoerter)
    baender_tab = b"".join(struct.pack("<Q", g) for g in baeume)
    files_off = INDEX_HEADER_SIZE
    chunks_off = files_off + len(dateien_tab)
    volumes_off = chunks_off + len(chunks_tab)
    strings_off = volumes_off + len(baender_tab)
    nutzlast = dateien_tab + chunks_tab + baender_tab + bytes(strings)
    kopf = bytearray(INDEX_HEADER_SIZE)
    kopf[0:8] = INDEX_MAGIC
    struct.pack_into("<IIBBH", kopf, 8, FORMAT_VERSION, INDEX_HEADER_SIZE, CHUNK_SHIFT, stufe, 0)
    struct.pack_into("<I", kopf, 20, anzahl_baender)
    kopf[24:40] = archiv
    struct.pack_into("<QQQQQQQQ", kopf, 40, len(eintraege), len(chunkwoerter), files_off, chunks_off, volumes_off,
                     strings_off, len(strings), ergebnis.logische_bytes)
    struct.pack_into("<I", kopf, 112, _crc(nutzlast))
    struct.pack_into("<I", kopf, 116, _crc(bytes(kopf[:112]) + b"\0" * 8 + bytes(kopf[120:])))
    index_pfad = os.path.join(ausgabe, INDEX_NAME)
    with open(index_pfad, "wb") as fh:
        fh.write(bytes(kopf) + nutzlast)
    ergebnis.index = INDEX_NAME
    melden("ampr_zstd: %d Dateien, %d Chunks (%d zstd, %d roh), %d Band/Baender, Stufe %d" % (
        ergebnis.dateien, ergebnis.chunks, ergebnis.zstd_chunks, ergebnis.roh_chunks, anzahl_baender, stufe))
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


def pruefen(ordner_packs: str, app0: str = "", *, melden: Melder = _stumm,
            abbruch: Callable[[], bool] = lambda: False,
            fortschritt: "Callable[[float], None] | None" = None) -> Index:
    """Prueft Index und Baender und - mit ``app0`` - jeden Chunk **Byte fuer Byte** gegen die Quelldateien.

    Ohne ``app0`` wird jeder Chunk nur entpackt (Frame-Pruefsumme, Laenge). Die Rueckgabe ist der Index.
    """
    index = index_laden(ordner_packs)
    handles: dict[int, Any] = {}
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
        for datei in index.dateien:
            if abbruch():
                raise ZstdPackFehler("ampr_pack.abgebrochen")
            quelle = None
            if app0:
                voll = os.path.join(os.path.abspath(app0), *datei.pfad.split("/"))
                try:
                    if os.path.getsize(voll) != datei.groesse:
                        raise ZstdPackFehler("ampr_zstd.quelle_anders: %s" % datei.pfad)
                    quelle = open(voll, "rb")
                except OSError as exc:
                    raise ZstdPackFehler("ampr_zstd.quelle_fehlt: %s" % datei.pfad) from exc
            try:
                for n, (offset, band, gespeichert, codec) in _datei_chunks(index, datei):
                    fh = handles[band]
                    fh.seek(offset)
                    gelesen = fh.read(gespeichert)
                    erwartet = min(CHUNK_SIZE, datei.groesse - n * CHUNK_SIZE)
                    if len(gelesen) != gespeichert:
                        raise ZstdPackFehler("ampr_zstd.band_kurz: %s" % datei.pfad)
                    if codec == CODEC_ZSTD:
                        rahmen_pruefen(gelesen, erwartet)
                    entpackt = chunk_entpacken(codec, gelesen, erwartet)
                    if quelle is not None and quelle.read(erwartet) != entpackt:
                        raise ZstdPackFehler("ampr_zstd.inhalt_anders: %s" % datei.pfad)
                    erledigt += erwartet
                    if fortschritt is not None:
                        fortschritt(min(1.0, erledigt / gesamt))
            finally:
                if quelle is not None:
                    quelle.close()
    finally:
        for fh in handles.values():
            fh.close()
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
    for name in namen:
        if abbruch():
            raise ZstdPackFehler("ampr_pack.abgebrochen")
        quelle = os.path.join(ausgabe, name)
        ziel = os.path.join(app0, name)
        erwartet = os.path.getsize(quelle)
        if os.path.exists(ziel):
            os.remove(ziel)
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
        voll = os.path.join(wurzel, *datei.pfad.split("/"))
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

    Vorhandene Dateien mit gleicher Groesse und gleichem Inhalt bleiben; ein abweichender Inhalt gilt als Fehler.
    Die Packdateien selbst werden nicht entfernt (das tut der Aufrufer nach Erfolg).
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
            voll = os.path.join(os.path.abspath(ziel), *datei.pfad.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            teil = voll + ".zstd-teil"
            with open(teil, "wb") as aus:
                for n, (offset, band, gespeichert, codec) in _datei_chunks(index, datei):
                    handles[band].seek(offset)
                    erwartet = min(CHUNK_SIZE, datei.groesse - n * CHUNK_SIZE)
                    aus.write(chunk_entpacken(codec, handles[band].read(gespeichert), erwartet))
                    erledigt += erwartet
                    if fortschritt is not None:
                        fortschritt(min(1.0, erledigt / gesamt))
            os.replace(teil, voll)
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
    for pfad, unter, dateien in os.walk(wurzel):
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
