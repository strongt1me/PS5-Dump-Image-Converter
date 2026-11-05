# -*- coding: utf-8 -*-
"""Abbild bearbeiten: Dateien eines entpackten Spiels umbenennen, loeschen, ersetzen und hinzufuegen.

Ein fertiges Abbild laesst sich nicht an Ort und Stelle aendern (``.exfat`` ohne freie Cluster, ``.ffpfsc`` ohne
Treiber, ``.ffpkg`` nur lesbar). Der Weg des Programms: Abbild **entpacken**, im Ordner aendern, **neu packen**.
Dieses Modul ist der mittlere Schritt - reine Dateiarbeit in einem Spielordner, ohne Oberflaeche, mit Pfadpruefung:

* Jeder Pfad ist relativ zur Wurzel des Spielordners und darf sie nie verlassen (``..``, absolute Pfade, Laufwerke,
  Verknuepfungen und Junctions werden abgewiesen).
* Namen muessen auf den Dateisystemen der Konsole und von Windows gleichermassen gueltig sein; Namensgleichheit gilt
  ohne Beachtung der Gross-/Kleinschreibung (exFAT, PFS), damit ``A.txt`` und ``a.txt`` nicht beide entstehen.
* ``eboot.bin`` und ``sce_sys/param.json`` sind geschuetzt: Loeschen und Umbenennen nur mit ``erzwingen=True``.
* Ersetzen schreibt erst eine Kopie neben die Zieldatei und tauscht sie dann atomar aus - bricht es ab, bleibt die
  alte Datei unversehrt.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

#: Dateien, ohne die ein Spiel nicht startet. Vergleich ohne Gross-/Kleinschreibung.
GESCHUETZT = ("eboot.bin", "sce_sys/param.json")

_UNGUELTIG = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVIERT = {"con", "prn", "aux", "nul", *("com%d" % i for i in range(1, 10)), *("lpt%d" % i for i in range(1, 10))}


class BearbeitenFehler(Exception):
    """Eine Aenderung wurde abgelehnt oder ist gescheitert. ``schluessel`` benennt den Grund (fuer die Oberflaeche)."""

    def __init__(self, schluessel: str, text: str = "") -> None:
        super().__init__(text or schluessel)
        self.schluessel = schluessel


@dataclass(frozen=True)
class Eintrag:
    """Eine Datei oder ein Ordner im Spielordner."""

    rel: str
    ist_ordner: bool
    groesse: int = 0


@dataclass(frozen=True)
class Aenderung:
    """Eine ausgefuehrte Aenderung - fuer die Zusammenfassung vor dem Neupacken."""

    art: str            # "loeschen" | "umbenennen" | "ersetzen" | "hinzufuegen" | "ordner"
    pfad: str
    ziel: str = ""


@dataclass
class Protokoll:
    """Alle Aenderungen einer Sitzung, in der Reihenfolge ihrer Ausfuehrung."""

    aenderungen: list[Aenderung] = field(default_factory=list)

    def merken(self, art: str, pfad: str, ziel: str = "") -> None:
        self.aenderungen.append(Aenderung(art, pfad, ziel))

    def anzahl(self) -> int:
        return len(self.aenderungen)

    def zaehlung(self) -> dict[str, int]:
        zaehler: dict[str, int] = {}
        for aenderung in self.aenderungen:
            zaehler[aenderung.art] = zaehler.get(aenderung.art, 0) + 1
        return zaehler


def name_pruefen(name: str) -> str:
    """Prueft einen einzelnen Datei- oder Ordnernamen und gibt ihn zurueck.

    Raises:
        BearbeitenFehler: leer, ``.``/``..``, ungueltige Zeichen, Punkt oder Leerzeichen am Ende, reservierter Name,
            oder laenger als 255 Zeichen.
    """
    if not isinstance(name, str) or not name.strip():
        raise BearbeitenFehler("bearbeiten.name_leer")
    if name in (".", "..") or name != name.strip() or name.endswith("."):
        raise BearbeitenFehler("bearbeiten.name_ungueltig", name)
    if _UNGUELTIG.search(name):
        raise BearbeitenFehler("bearbeiten.name_ungueltig", name)
    if name.split(".", 1)[0].lower() in _RESERVIERT:
        raise BearbeitenFehler("bearbeiten.name_reserviert", name)
    if len(name) > 255:
        raise BearbeitenFehler("bearbeiten.name_zu_lang", name)
    return name


def rel_normalisieren(rel: str) -> str:
    """Macht aus ``rel`` einen sauberen relativen Pfad mit ``/``; leerer Pfad = die Wurzel (``""``).

    Raises:
        BearbeitenFehler: absoluter Pfad, Laufwerk, ``..`` oder ein ungueltiger Bestandteil.
    """
    text = str(rel or "").replace("\\", "/").strip("/")
    if not text or text == ".":
        return ""
    if re.match(r"^[A-Za-z]:", text) or str(rel or "").startswith(("/", "\\")):
        raise BearbeitenFehler("bearbeiten.pfad_ausserhalb", str(rel))
    teile = [t for t in text.split("/") if t not in ("", ".")]
    for teil in teile:
        if teil == "..":
            raise BearbeitenFehler("bearbeiten.pfad_ausserhalb", str(rel))
        name_pruefen(teil)
    return "/".join(teile)


def _ist_verknuepfung(pfad: str) -> bool:
    ist_knoten = getattr(os.path, "isjunction", lambda _p: False)
    return os.path.islink(pfad) or bool(ist_knoten(pfad))


def aufloesen(wurzel: str, rel: str) -> str:
    """Der absolute Pfad zu ``rel`` unter ``wurzel`` - nur, wenn er die Wurzel nicht verlaesst.

    Auch ein Bestandteil, der eine Verknuepfung oder Junction ist, wird abgewiesen: Ein entpacktes Abbild hat keine,
    und ein Weg hindurch koennte aus dem Ordner herausfuehren.
    """
    sauber = rel_normalisieren(rel)
    basis = os.path.realpath(wurzel)
    ziel = os.path.join(basis, *sauber.split("/")) if sauber else basis
    aktuell = basis
    for teil in sauber.split("/") if sauber else []:
        aktuell = os.path.join(aktuell, teil)
        if os.path.lexists(aktuell) and _ist_verknuepfung(aktuell):
            raise BearbeitenFehler("bearbeiten.verknuepfung", sauber)
    echt = os.path.realpath(ziel)
    if echt != basis and not echt.startswith(basis + os.sep):
        raise BearbeitenFehler("bearbeiten.pfad_ausserhalb", rel)
    return ziel


def ist_geschuetzt(rel: str) -> bool:
    try:
        sauber = rel_normalisieren(rel).lower()
    except BearbeitenFehler:
        return False
    return sauber in GESCHUETZT


def auflisten(wurzel: str) -> list[Eintrag]:
    """Alle Dateien und Ordner unter ``wurzel``, nach Pfad sortiert (Ordner vor ihrem Inhalt).

    Verknuepfungen werden nicht verfolgt (nicht betreten); sie erscheinen als Eintrag, damit man sie sieht.
    """
    ergebnis: list[Eintrag] = []
    basis = os.path.abspath(wurzel)

    def _gehen(ordner: str, praefix: str) -> None:
        try:
            eintraege = sorted(os.scandir(ordner), key=lambda e: e.name.lower())
        except OSError:
            return
        for e in eintraege:
            rel = (praefix + "/" + e.name) if praefix else e.name
            if e.is_symlink() or _ist_verknuepfung(e.path):
                ergebnis.append(Eintrag(rel, False, 0))
            elif e.is_dir(follow_symlinks=False):
                ergebnis.append(Eintrag(rel, True, 0))
                _gehen(e.path, rel)
            else:
                try:
                    groesse = e.stat(follow_symlinks=False).st_size
                except OSError:
                    groesse = 0
                ergebnis.append(Eintrag(rel, False, groesse))

    _gehen(basis, "")
    return ergebnis


def _gleicher_name_im_ordner(ordner: str, name: str, ausser: str = "") -> bool:
    """Gibt es im ``ordner`` schon einen Eintrag desselben Namens (ohne Beachtung der Schreibung)?"""
    kleiner = name.lower()
    try:
        for e in os.scandir(ordner):
            if e.name.lower() == kleiner and e.name != ausser:
                return True
    except OSError:
        return False
    return False


def _geschuetzt_pruefen(rel: str, erzwingen: bool) -> None:
    if ist_geschuetzt(rel) and not erzwingen:
        raise BearbeitenFehler("bearbeiten.geschuetzt", rel)


def _enthaelt_geschuetztes(wurzel: str, rel: str) -> bool:
    """Liegt unter dem Ordner ``rel`` eine geschuetzte Datei?"""
    praefix = rel_normalisieren(rel).lower() + "/"
    return any(g.startswith(praefix) for g in GESCHUETZT)


def loeschen(wurzel: str, rel: str, *, erzwingen: bool = False, protokoll: Protokoll | None = None) -> None:
    """Loescht eine Datei oder einen ganzen Ordner (endgueltig, im entpackten Arbeitsordner)."""
    sauber = rel_normalisieren(rel)
    if not sauber:
        raise BearbeitenFehler("bearbeiten.wurzel")
    _geschuetzt_pruefen(sauber, erzwingen)
    pfad = aufloesen(wurzel, sauber)
    if not os.path.lexists(pfad):
        raise BearbeitenFehler("bearbeiten.nicht_gefunden", sauber)
    if os.path.isdir(pfad) and _enthaelt_geschuetztes(wurzel, sauber) and not erzwingen:
        raise BearbeitenFehler("bearbeiten.geschuetzt", sauber)
    try:
        if os.path.isdir(pfad):
            shutil.rmtree(pfad)
        else:
            os.unlink(pfad)
    except OSError as exc:
        raise BearbeitenFehler("bearbeiten.io", str(exc)) from exc
    if protokoll is not None:
        protokoll.merken("loeschen", sauber)


def umbenennen(wurzel: str, rel: str, neuer_name: str, *, erzwingen: bool = False,
               protokoll: Protokoll | None = None) -> str:
    """Benennt eine Datei oder einen Ordner um (im selben Ordner). Gibt den neuen relativen Pfad zurueck."""
    sauber = rel_normalisieren(rel)
    if not sauber:
        raise BearbeitenFehler("bearbeiten.wurzel")
    neu = name_pruefen(neuer_name)
    _geschuetzt_pruefen(sauber, erzwingen)
    pfad = aufloesen(wurzel, sauber)
    if not os.path.lexists(pfad):
        raise BearbeitenFehler("bearbeiten.nicht_gefunden", sauber)
    if os.path.isdir(pfad) and _enthaelt_geschuetztes(wurzel, sauber) and not erzwingen:
        raise BearbeitenFehler("bearbeiten.geschuetzt", sauber)
    ordner, alt = os.path.split(pfad)
    if neu == alt:
        raise BearbeitenFehler("bearbeiten.gleicher_name", neu)
    # Nur die Schreibung aendern ist erlaubt (a.txt -> A.txt), ein zweiter Eintrag desselben Namens nicht.
    if _gleicher_name_im_ordner(ordner, neu, ausser=alt) or (
            neu.lower() != alt.lower() and os.path.lexists(os.path.join(ordner, neu))):
        raise BearbeitenFehler("bearbeiten.name_vergeben", neu)
    ziel = os.path.join(ordner, neu)
    try:
        os.rename(pfad, ziel)
    except OSError as exc:
        raise BearbeitenFehler("bearbeiten.io", str(exc)) from exc
    teile = sauber.split("/")
    neu_rel = "/".join([*teile[:-1], neu])
    if protokoll is not None:
        protokoll.merken("umbenennen", sauber, neu_rel)
    return neu_rel


def _quelldatei_pruefen(quelle: str) -> str:
    pfad = os.path.abspath(str(quelle or ""))
    if not os.path.isfile(pfad) or _ist_verknuepfung(pfad):
        raise BearbeitenFehler("bearbeiten.quelle_fehlt", str(quelle))
    return pfad


def _atomar_kopieren(quelle: str, ziel: str) -> None:
    """Kopiert ``quelle`` nach ``ziel`` ueber eine Zwischendatei im selben Ordner; ``ziel`` bleibt bis zuletzt heil."""
    ordner = os.path.dirname(ziel)
    fd, zwischen = tempfile.mkstemp(prefix=".bearbeiten_", suffix=".tmp", dir=ordner)
    os.close(fd)
    try:
        shutil.copyfile(quelle, zwischen)
        os.replace(zwischen, ziel)
    except OSError as exc:
        raise BearbeitenFehler("bearbeiten.io", str(exc)) from exc
    finally:
        if os.path.exists(zwischen):
            try:
                os.unlink(zwischen)
            except OSError:
                pass


def ersetzen(wurzel: str, rel: str, quelle: str, *, protokoll: Protokoll | None = None) -> None:
    """Ersetzt den Inhalt der Datei ``rel`` durch die Datei ``quelle`` (Name und Ort bleiben)."""
    sauber = rel_normalisieren(rel)
    if not sauber:
        raise BearbeitenFehler("bearbeiten.wurzel")
    pfad = aufloesen(wurzel, sauber)
    if not os.path.isfile(pfad):
        raise BearbeitenFehler("bearbeiten.keine_datei", sauber)
    _atomar_kopieren(_quelldatei_pruefen(quelle), pfad)
    if protokoll is not None:
        protokoll.merken("ersetzen", sauber, os.path.basename(str(quelle)))


def hinzufuegen(wurzel: str, ordner_rel: str, quelle: str, name: str = "", *,
                protokoll: Protokoll | None = None) -> str:
    """Legt die Datei ``quelle`` als neue Datei in ``ordner_rel`` ab (unter ``name`` oder dem eigenen Namen).

    Gibt den relativen Pfad der neuen Datei zurueck. Eine schon vorhandene Datei (gleicher Name, ohne Beachtung der
    Schreibung) wird nicht ueberschrieben - dafuer gibt es :func:`ersetzen`.
    """
    ordner_sauber = rel_normalisieren(ordner_rel)
    ordner = aufloesen(wurzel, ordner_sauber)
    if not os.path.isdir(ordner):
        raise BearbeitenFehler("bearbeiten.kein_ordner", ordner_sauber)
    datei = _quelldatei_pruefen(quelle)
    neu = name_pruefen(name or os.path.basename(datei))
    if _gleicher_name_im_ordner(ordner, neu):
        raise BearbeitenFehler("bearbeiten.name_vergeben", neu)
    _atomar_kopieren(datei, os.path.join(ordner, neu))
    neu_rel = "/".join([p for p in (ordner_sauber, neu) if p])
    if protokoll is not None:
        protokoll.merken("hinzufuegen", neu_rel, os.path.basename(datei))
    return neu_rel


def ordner_anlegen(wurzel: str, ordner_rel: str, name: str, *, protokoll: Protokoll | None = None) -> str:
    """Legt einen neuen, leeren Ordner an. Gibt seinen relativen Pfad zurueck."""
    ordner_sauber = rel_normalisieren(ordner_rel)
    ordner = aufloesen(wurzel, ordner_sauber)
    if not os.path.isdir(ordner):
        raise BearbeitenFehler("bearbeiten.kein_ordner", ordner_sauber)
    neu = name_pruefen(name)
    if _gleicher_name_im_ordner(ordner, neu):
        raise BearbeitenFehler("bearbeiten.name_vergeben", neu)
    try:
        os.mkdir(os.path.join(ordner, neu))
    except OSError as exc:
        raise BearbeitenFehler("bearbeiten.io", str(exc)) from exc
    neu_rel = "/".join([p for p in (ordner_sauber, neu) if p])
    if protokoll is not None:
        protokoll.merken("ordner", neu_rel)
    return neu_rel


def spiel_pruefen(wurzel: str) -> list[str]:
    """Meldet, was dem Spielordner nach der Bearbeitung fehlt: die Schluessel der fehlenden geschuetzten Dateien.

    Leer = in Ordnung. Das Programm warnt davor, ein solches Abbild zu packen, verbietet es aber nicht (ein
    Homebrew-Ordner kann anders aufgebaut sein).
    """
    fehlt: list[str] = []
    for rel in GESCHUETZT:
        try:
            ok = os.path.isfile(aufloesen(wurzel, rel))
        except BearbeitenFehler:
            ok = False
        if not ok:
            fehlt.append(rel)
    return fehlt
