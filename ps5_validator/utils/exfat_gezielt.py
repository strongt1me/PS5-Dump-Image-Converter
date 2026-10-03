# -*- coding: utf-8 -*-
"""Gezielt in einem exFAT-Abbild lesen: einzelne Dateien und Ordnerinhalte, ohne den ganzen Baum zu laden.

**Warum es das gibt.** Die Engine (``mkpfs.exfat.ExfatReader``) liefert Dateien nur ueber ``iter_files()`` und
``root_entries()`` - und beide bauen zuerst den *ganzen* Verzeichnisbaum auf: Jeder Verzeichniscluster des Abbilds
wird gelesen, auch wenn der Aufrufer nur drei Dateien sucht. Die Bibliothek braucht je Abbild aber genau das:
``sce_sys/param.json``, ``sce_sys/icon0.png`` und, fuer die Einbauten, den Inhalt von ``fakelib``/``fakelib2``.
An den Abbildern des Nutzers (``E:\\exFAT Games``, am 03.10.2026 gemessen) dauerte der erste Aufruf fuer
``DIRT5 (06.004.000).exfat`` (104 GB, tausende Verzeichnisse) **mehr als vier Minuten** - und derselbe Baum
wurde fuer die Einbauten noch einmal gelesen. Bei 23 Abbildern war das ein Nachmittag.

Hier werden nur die Ordner gelesen, die auf dem Weg liegen (Wurzel, ``sce_sys``, ``fakelib`` ...): eine
Handvoll Cluster, gleich gross fuer ein kleines und ein riesiges Spiel.

**Was gleich bleibt.** Die Ergebnisse sind die der Engine. ``metadaten`` ruft ``read_game_metadata`` selbst auf und
tauscht dabei nur die Funktion aus, die den ganzen Baum durchlaeuft, gegen drei gezielte Zugriffe; sucht
wird exakt dieselbe Pfadangabe (``sce_sys/param.json``, ``sce_sys/icon0.png``, ``fakelib/libSceAmpr.sprx`` -
ohne Beachtung der Gross- und Kleinschreibung, wie exFAT selbst). Die Tests halten beides gegen die
Engine (``test_exfat_gezielt``).

Gebaut ist es auf der Aufteilung der Engine in Verzeichniscluster (``_read_directory_entries``); die Aufbereitung der
Eintraege (Datei-, Strom- und Namenseintrag) folgt der exFAT-Spezifikation und ``ExfatReader._walk_directory``
- nur ohne den Abstieg in jeden Unterordner. Fehlt eine der Engine-Funktionen (neue Fassung), tut dieses Modul
nichts: Die Aufrufer fallen auf den bisherigen Weg zurueck.
"""
from __future__ import annotations

import os
import struct
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .logger import get_logger

log = get_logger(__name__)

# exFAT-Spezifikation: Eintragsarten eines Verzeichnisses, Attribut "Ordner", Merker "keine FAT-Kette".
_EINTRAG_DATEI = 0x85
_EINTRAG_STROM = 0xC0
_EINTRAG_NAME = 0xC1
_ATTR_ORDNER = 0x10
_FLAG_OHNE_KETTE = 0x02

#: Mehr als so viele Bytes liest ein Zugriff nie (``param.json`` und Titelbild sind weit darunter).
STANDARD_GRENZE = 8 * 1024 * 1024

#: Huellen vor der Spielwurzel, wie sie manche Abbilder tragen (``app0/fakelib/...``).
HUELLEN: tuple[str, ...] = ("app0", "uroot")


@dataclass(frozen=True)
class Eintrag:
    """Ein Eintrag eines Verzeichnisses - Datei oder Ordner."""

    name: str
    ist_ordner: bool
    erster_cluster: int
    laenge: int
    ohne_kette: bool


class GezielterZugriff:
    """Liest Ordner und Dateien eines exFAT-Abbilds gezielt - jeder Ordner hoechstens einmal.

    Args:
        leser: Ein ``mkpfs.exfat.ExfatReader`` (oder etwas mit derselben Schnittstelle:
            ``geometry.root_dir_cluster``, ``_read_directory_entries``, ``read_file``).
    """

    def __init__(self, leser: Any) -> None:
        self._leser = leser
        self._ordner: dict[tuple[int, bool, int], list[Eintrag]] = {}
        #: Wie oft ein Verzeichnis wirklich von der Platte gelesen wurde - fuer die Tests.
        self.gelesene_ordner = 0

    # --- Ordner ------------------------------------------------------------------------------------
    def auflisten(self, ordner: Eintrag | None = None) -> list[Eintrag]:
        """Der Inhalt eines Ordners (``None`` = die Wurzel) - nur diese Ebene, nicht darunter."""
        if ordner is None:
            schluessel = (int(self._leser.geometry.root_dir_cluster), False, 0)
        else:
            schluessel = (ordner.erster_cluster, ordner.ohne_kette, ordner.laenge)
        gemerkt = self._ordner.get(schluessel)
        if gemerkt is None:
            rohe = list(self._leser._read_directory_entries(*schluessel))
            self.gelesene_ordner += 1
            gemerkt = _eintraege(rohe)
            self._ordner[schluessel] = gemerkt
        return gemerkt

    def suchen(self, *teile: str) -> Eintrag | None:
        """Der Eintrag zu einem Pfad ab der Wurzel - ohne Beachtung der Schreibung, Ordner fuer Ordner."""
        aktuell: Eintrag | None = None
        for nummer, teil in enumerate(teile):
            kleiner = teil.lower()
            treffer = next((e for e in self.auflisten(aktuell) if e.name.lower() == kleiner), None)
            if treffer is None:
                return None
            if nummer < len(teile) - 1 and not treffer.ist_ordner:
                return None
            aktuell = treffer
        return aktuell

    # --- Dateien -----------------------------------------------------------------------------------
    def lesen(self, datei: Eintrag, grenze: int = STANDARD_GRENZE) -> bytes | None:
        """Die Bytes einer Datei - ``None``, wenn sie leer, ein Ordner oder groesser als ``grenze`` ist."""
        if datei.ist_ordner or not 0 < datei.laenge <= grenze:
            return None
        eintrag_klasse = getattr(sys.modules.get(type(self._leser).__module__), "ExfatEntry", None)
        if eintrag_klasse is None:
            return None
        engine_eintrag = eintrag_klasse(
            name=datei.name, rel_path=datei.name, is_dir=False, first_cluster=datei.erster_cluster,
            length=datei.laenge, no_fat_chain=datei.ohne_kette)
        return b"".join(self._leser.read_file(engine_eintrag))


def _eintraege(rohe: list[bytes]) -> list[Eintrag]:
    """Die Dateien und Ordner aus den rohen 32-Byte-Eintraegen - wie ``ExfatReader._walk_directory``, ohne Abstieg."""
    ergebnis: list[Eintrag] = []
    nummer = 0
    while nummer < len(rohe):
        kopf = rohe[nummer]
        if kopf[0] != _EINTRAG_DATEI:
            nummer += 1
            continue
        folgen = kopf[1]
        attribute = struct.unpack_from("<H", kopf, 0x04)[0]
        zusatz = rohe[nummer + 1:nummer + 1 + folgen]
        nummer += 1 + folgen
        if len(zusatz) < folgen or not zusatz:
            continue
        strom = zusatz[0]
        if strom[0] != _EINTRAG_STROM:
            continue
        namenslaenge = strom[3]
        einheiten = bytearray()
        for rest in zusatz[1:]:
            if rest[0] == _EINTRAG_NAME:
                einheiten += rest[2:32]
        ergebnis.append(Eintrag(
            name=einheiten.decode("utf-16-le", errors="replace")[:namenslaenge],
            ist_ordner=bool(attribute & _ATTR_ORDNER),
            erster_cluster=struct.unpack_from("<I", strom, 0x14)[0],
            laenge=struct.unpack_from("<Q", strom, 0x18)[0],
            ohne_kette=bool(strom[1] & _FLAG_OHNE_KETTE)))
    return ergebnis


# ---------------------------------------------------------------------------
# Angaben und Titelbild (Ersatz fuer den Rundgang der Engine)
# ---------------------------------------------------------------------------

def fuellen(leser: Any, meta: Any, engine: Any) -> None:
    """Fuellt ``meta`` aus ``sce_sys/param.json`` und ``sce_sys/icon0.png`` - wie ``_fill_from_exfat_reader`` der Engine.

    Dieselben drei Pfade, dieselben Grenzen, dieselbe Auswertung (``engine._fill_from_param_json``), nur ohne
    den ganzen Baum zu lesen. Fehlt beides, bleibt ``meta`` wie es ist - die Engine haette in diesem Fall
    nach dem Rundgang dasselbe festgestellt.

    Raises:
        Was die Auswertung der ``param.json`` wirft (kaputtes JSON) - die Engine meldet es als ``meta.error``.
    """
    zugriff = GezielterZugriff(leser)
    meta.has_apr_emu = zugriff.suchen("fakelib", "libSceAmpr.sprx") is not None
    param = zugriff.suchen("sce_sys", "param.json")
    grenze_param = int(getattr(engine, "_MAX_PARAM_SIZE", 1 << 20))
    if param is not None and 0 < param.laenge <= grenze_param:
        daten = zugriff.lesen(param, grenze_param)
        if daten is not None:
            engine._fill_from_param_json(daten, meta)
    icon = zugriff.suchen("sce_sys", "icon0.png")
    grenze_icon = int(getattr(engine, "_MAX_ICON_SIZE", 4 << 20))
    if icon is not None and 0 < icon.laenge <= grenze_icon:
        bild = zugriff.lesen(icon, grenze_icon)
        if bild is not None and engine._is_png(bild):
            meta.icon_bytes = bild


_SPERRE = threading.Lock()


def metadaten(pfad: str, engine: Any) -> Any | None:
    """``read_game_metadata`` der Engine fuer ``.exfat``, ``.ffpfs`` und ``.ffpfsc`` - ohne den ganzen Baum.

    Die Engine ruft fuer ein exFAT (direkt oder im Abbild) ``_fill_from_exfat_reader`` auf, und die liest jeden
    Verzeichniscluster. Fuer die Dauer dieses einen Aufrufs steht an ihrer Stelle :func:`fuellen`; alles andere
    (Kopf des Abbilds, Inodes, PFS ohne exFAT, Fehlermeldungen) bleibt die Engine. Der Austausch laeuft unter
    einer Sperre und wird im ``finally`` zurueckgenommen.

    Args:
        pfad: Die Datei.
        engine: Das Modul ``mkpfs.game_metadata``.

    Returns:
        Das ``GameMetadata`` der Engine - oder ``None``, wenn die Endung nicht passt oder die Engine
        die benoetigten Namen nicht (mehr) hat; dann soll der Aufrufer ``read_game_metadata`` selbst rufen.
    """
    if os.path.splitext(str(pfad))[1].lower() not in (".exfat", ".ffpfs", ".ffpfsc"):
        return None
    original = getattr(engine, "_fill_from_exfat_reader", None)
    lesen = getattr(engine, "read_game_metadata", None)
    if (original is None or lesen is None or not hasattr(engine, "_fill_from_param_json")
            or not hasattr(engine, "_is_png")):
        return None

    def _gezielt(leser: Any, meta: Any) -> None:
        fuellen(leser, meta, engine)

    with _SPERRE:
        engine._fill_from_exfat_reader = _gezielt
        try:
            return lesen(Path(pfad))
        finally:
            engine._fill_from_exfat_reader = original


# ---------------------------------------------------------------------------
# Einbauten (Ersatz fuer die Liste aller Dateien)
# ---------------------------------------------------------------------------

def einbau_pfade(leser: Any, ordner: Iterable[str]) -> list[str]:
    """Die Pfade, aus denen sich die Einbauten ergeben - ohne die Liste aller Dateien.

    ``bibliothek.einbauten_bewerten`` liest aus den Pfaden nur zweierlei: die Dateien **direkt in der
    Wurzel** (das Asset-Pack) und den Inhalt der Bibliotheksordner (``fakelib2``, ``fakelib``) samt der
    ``fw<NN>``-Ordner darin (BACKPORT). Das sind hoechstens die Wurzel, die zwei Bibliotheksordner und deren
    Unterordner - nicht der Baum des Spiels. Eine Huelle vor der Spielwurzel (``app0/``, ``uroot/``)
    wird wie bisher mitgelesen.

    Args:
        leser: Der ``ExfatReader``.
        ordner: Die Namen der Bibliotheksordner (``bibliothek.FAKELIB_REIHENFOLGE``).

    Returns:
        Relative Pfade mit Schraegstrich, wie ``iter_files`` sie gegeben haette - soweit sie fuer die
        Einbauten zaehlen.
    """
    bibliotheken = {str(name).lower() for name in ordner}
    zugriff = GezielterZugriff(leser)
    pfade: list[str] = []

    def _wurzel(vor: str, ordner_eintrag: Eintrag | None) -> None:
        inhalt = zugriff.auflisten(ordner_eintrag)
        for eintrag in inhalt:
            if not eintrag.ist_ordner:
                pfade.append(vor + eintrag.name)
        for eintrag in inhalt:
            if eintrag.ist_ordner and eintrag.name.lower() in bibliotheken:
                for unter in zugriff.auflisten(eintrag):
                    if not unter.ist_ordner:
                        pfade.append("%s%s/%s" % (vor, eintrag.name, unter.name))
                        continue
                    for datei in zugriff.auflisten(unter):
                        if not datei.ist_ordner:
                            pfade.append("%s%s/%s/%s" % (vor, eintrag.name, unter.name, datei.name))

    wurzel = zugriff.auflisten(None)
    _wurzel("", None)
    for eintrag in wurzel:
        if eintrag.ist_ordner and eintrag.name.lower() in HUELLEN:
            _wurzel(eintrag.name + "/", eintrag)
    return pfade
