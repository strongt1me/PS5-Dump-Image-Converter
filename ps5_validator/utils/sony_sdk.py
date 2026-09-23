# -*- coding: utf-8 -*-
"""Der zweite Bauweg: PKG bauen mit Sonys Publishing Tools aus ``libs/sdk``.

Der mitgelieferte Weg baut mit ``prosperopkg`` (LibProsperoPkg). Wer den
SDK-Baukasten besitzt, kann stattdessen **Sonys eigene Befehlszeile**
benutzen - ein anderes Programm, kein Austausch einer Bibliothek. Deshalb
steht das hier und nicht in ``eigene_bibliotheken``.

**Der Baukasten wird nicht mitgeliefert und darf nie weitergegeben werden.**
``prospero-pub-cmd.exe``, ``libScePubTools.dll`` und die Wandler unter
``toolchain/ext`` gehoeren Sony. Sie duerfen lokal liegen (``libs`` ist
gitignoriert), nicht im Buendel und nicht in einem Release.

**Erwarteter Aufbau** (so, wie der Nutzer ihn am 23.09.2026 vorgelegt hat)::

    libs/sdk/
      toolchain/prospero-pub-cmd.exe      <- Pflicht
      toolchain/libScePubTools.dll        <- Pflicht
      toolchain/ext/da.exe fa.exe p2d.exe ric.exe sc2.exe
      toolchain/ext/ispc_texcomp.dll libatrac9.dll
      scripts/create-gp5-from-folder.py
      build-from-folder.ps1  build.bat  build-gui.ps1 ...

**Ablauf** (zwei Schritte, wie ``build-from-folder.ps1`` sie geht):

1. Ein GP5-Projekt schreiben (``gp5_project``) - es beschreibt Quellordner,
   Content-ID, Passcode und Volume-Typ.
2. ``prospero-pub-cmd.exe img_create --oformat nwonly <projekt.gp5> <ziel>``
   komprimiert, erzeugt PlayGo und schreibt das Paket.

**Was dieses Modul NICHT kann und nicht behauptet:** Ob das entstehende
Paket auf der Konsole laeuft, haengt am Baukasten selbst. Eine unveraenderte
Publishing-Tools-Fassung schreibt ein **signiertes, verschluesseltes** Paket -
eine gejailbreakte Konsole nimmt das nicht an. Die im Umlauf befindlichen
Baukaesten tragen dafuer ein **gepatchtes** ``prospero-pub-cmd.exe``
("plaintext"-Profil). Dieses Modul prueft den Unterschied nicht; es ruft auf,
was da ist, und reicht jede Zeile der Ausgabe weiter.

Gemessene Tatsachen aus fremden Messreihen (nicht unsere, als Wissen
uebernommen - siehe ``reference_psviethoa_fpkg_builder``):

* Dateinamen: Jedes druckbare ASCII-Zeichen ist erlaubt **ausser ``%`` und
  ``;``**; alles Nicht-ASCII und Namen, die auf einen Punkt enden, weist
  ``img_create`` ab ("invalid attribute value dst_path"). Das faellt sonst
  erst nach dem Komprimieren auf - deshalb prueft :func:`namen_pruefen` das
  vorher.
* ``--compression_level`` nimmt -4 bis 9, Vorgabe des Baukastens ist 7.

Nur Standardbibliothek.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("PS5Converter.sony_sdk")

#: Der Unterordner in ``libs``, in dem der Baukasten erwartet wird.
ORDNER = "sdk"

#: Ohne diese beiden geht gar nichts.
PFLICHT = (
    os.path.join("toolchain", "prospero-pub-cmd.exe"),
    os.path.join("toolchain", "libScePubTools.dll"),
)

#: Die Wandler fuer Bilder, Audio und Texturen. Fehlen sie, baut der SDK
#: trotzdem - er kann dann nur nichts umwandeln.
KUER = (
    os.path.join("toolchain", "ext", "da.exe"),
    os.path.join("toolchain", "ext", "fa.exe"),
    os.path.join("toolchain", "ext", "p2d.exe"),
    os.path.join("toolchain", "ext", "ric.exe"),
    os.path.join("toolchain", "ext", "sc2.exe"),
    os.path.join("toolchain", "ext", "ispc_texcomp.dll"),
    os.path.join("toolchain", "ext", "libatrac9.dll"),
)

#: Zeichen, die ``img_create`` im Dateinamen abweist (gemessen).
VERBOTENE_ZEICHEN = ("%", ";")

#: Was der Baukasten von Haus aus einstellt.
STANDARD_STUFE = 7
STUFE_MIN, STUFE_MAX = -4, 9


class SdkFehler(RuntimeError):
    """Der Baukasten fehlt, bricht ab oder antwortet unverstaendlich."""


@dataclass
class SdkStand:
    """Liegt unter ``libs/sdk`` ein brauchbarer Baukasten?"""

    pfad: str = ""
    fehlende: "list[str]" = field(default_factory=list)
    fehlende_kuer: "list[str]" = field(default_factory=list)

    @property
    def vorhanden(self) -> bool:
        """Nur wahr, wenn beide Pflichtdateien da sind."""
        return bool(self.pfad) and not self.fehlende

    @property
    def vollstaendig(self) -> bool:
        return self.vorhanden and not self.fehlende_kuer

    @property
    def programm(self) -> str:
        if not self.vorhanden:
            return ""
        return os.path.join(self.pfad, PFLICHT[0])


def sdk_ordner(libs_ordner: str = "") -> str:
    """Der Pfad von ``libs/sdk`` - leer, wenn es ihn nicht gibt."""
    from ps5_validator.utils import eigene_bibliotheken

    wurzel = libs_ordner or eigene_bibliotheken.ordner_finden()
    if not wurzel:
        return ""
    pfad = os.path.join(wurzel, ORDNER)
    return pfad if os.path.isdir(pfad) else ""


def pruefen(libs_ordner: str = "") -> SdkStand:
    """Was liegt da, und was fehlt?

    Returns:
        Einen :class:`SdkStand`. ``vorhanden`` sagt, ob gebaut werden kann;
        ``fehlende_kuer`` nennt die Wandler, die fehlen.
    """
    pfad = sdk_ordner(libs_ordner)
    if not pfad:
        return SdkStand()
    fehlt = [teil for teil in PFLICHT
             if not os.path.isfile(os.path.join(pfad, teil))]
    fehlt_kuer = [teil for teil in KUER
                  if not os.path.isfile(os.path.join(pfad, teil))]
    return SdkStand(pfad=pfad, fehlende=fehlt, fehlende_kuer=fehlt_kuer)


def name_ist_zulaessig(name: str) -> bool:
    """Nimmt ``img_create`` diesen Dateinamen an?

    Gemessen (fremde Messreihe): druckbares ASCII ausser ``%`` und ``;``,
    kein Nicht-ASCII, kein abschliessender Punkt.
    """
    text = str(name or "")
    if not text or text.endswith("."):
        return False
    for zeichen in text:
        if ord(zeichen) < 32 or ord(zeichen) > 126:
            return False
        if zeichen in VERBOTENE_ZEICHEN:
            return False
    return True


def namen_pruefen(quelle: str, grenze: int = 50,
                  melden: "Callable[[int], None] | None" = None
                  ) -> "list[str]":
    """Welche Dateien im Quellordner wuerde der SDK abweisen?

    Lieber hier eine Sekunde, als nach dem Komprimieren eines 50-GB-Titels
    an "invalid attribute value dst_path" zu scheitern.

    Args:
        quelle: Der Spielordner.
        grenze: Nach so vielen Treffern wird abgebrochen - fuer eine Liste
            im Fenster reicht das, und ein voellig falscher Ordner erzeugt
            keine endlose Aufzaehlung.
        melden: Bekommt die Zahl der bisher geprueften Dateien.

    Returns:
        Die beanstandeten Pfade, relativ zu ``quelle``.
    """
    treffer: "list[str]" = []
    gezaehlt = 0
    for wurzel, ordner, dateien in os.walk(quelle):
        for name in list(ordner) + dateien:
            gezaehlt += 1
            if melden is not None and gezaehlt % 2000 == 0:
                melden(gezaehlt)
            if name_ist_zulaessig(name):
                continue
            voll = os.path.join(wurzel, name)
            treffer.append(os.path.relpath(voll, quelle))
            if len(treffer) >= grenze:
                if melden is not None:
                    melden(gezaehlt)
                return treffer
    if melden is not None:
        melden(gezaehlt)
    return treffer


def projekt_schreiben(quelle: str, ziel_gp5: str, content_id: str = "",
                      passcode: str = "", art: str = "app") -> str:
    """Schreibt das GP5-Projekt, das ``img_create`` bekommt.

    Returns:
        Den Pfad der geschriebenen Datei.
    """
    from ps5_validator.utils import gp5_project

    typ = {
        "app": gp5_project.Gp5VolumeType.APP,
        "patch": gp5_project.Gp5VolumeType.PATCH,
        "ac": gp5_project.Gp5VolumeType.AC,
    }.get(str(art or "app").lower(), gp5_project.Gp5VolumeType.APP)

    projekt = gp5_project.create_project(
        typ, os.path.abspath(quelle),
        passcode=passcode or gp5_project.DEFAULT_PASSCODE,
        content_id=content_id)
    os.makedirs(os.path.dirname(os.path.abspath(ziel_gp5)), exist_ok=True)
    gp5_project.write_to(projekt, ziel_gp5)
    return ziel_gp5


def befehl_bauen(programm: str, projekt: str, zielordner: str,
                 stufe: "int | None" = None,
                 grundpaket: str = "",
                 oformat: str = "nwonly") -> "list[str]":
    """Die Befehlszeile fuer ``img_create`` - ohne sie auszufuehren.

    Getrennt vom Lauf, damit sie sich pruefen laesst, ohne den Baukasten zu
    besitzen (und damit das Fenster zeigen kann, was es aufrufen wuerde).

    Args:
        stufe: ``--compression_level`` (-4 bis 9). ``None`` laesst die
            Vorgabe des Baukastens stehen (7).
        grundpaket: Fuer ein Update: das installierte Basispaket
            (``--ref_pkg_path``). Das Ergebnis ist dann ein Delta, das genau
            an dieses Paket gebunden ist.
    """
    befehl = [str(programm), "img_create"]
    if oformat:
        befehl += ["--oformat", str(oformat)]
    if stufe is not None:
        wert = max(STUFE_MIN, min(STUFE_MAX, int(stufe)))
        befehl += ["--compression_level", str(wert)]
    if grundpaket:
        befehl += ["--ref_pkg_path", str(grundpaket)]
    befehl += [str(projekt), str(zielordner)]
    return befehl


def bauen(stand: SdkStand, projekt: str, zielordner: str,
          stufe: "int | None" = None, grundpaket: str = "",
          melden: "Callable[[str], None] | None" = None,
          zeitgrenze: float = 7200.0,
          prozess_ablage: "dict | None" = None) -> "tuple[int, list[str]]":
    """Ruft Sonys Befehlszeile auf und reicht jede Zeile weiter.

    Derselbe Aufbau wie ``prosperopkg._laufen_lassen``: eigener Wecker fuer
    die Zeitgrenze (die Ausgabeschleife blockiert sonst ohne Frist), der
    laufende Prozess landet in ``prozess_ablage`` fuer den Abbruch.

    Raises:
        SdkFehler: wenn der Baukasten fehlt oder nicht startet.
    """
    if not stand.vorhanden:
        raise SdkFehler("Unter libs/%s liegt kein vollstaendiger Baukasten: %s"
                        % (ORDNER, ", ".join(stand.fehlende) or "Ordner fehlt"))
    if sys.platform != "win32":
        raise SdkFehler("Der Baukasten ist ein Windows-Programm "
                        "(prospero-pub-cmd.exe).")

    os.makedirs(zielordner, exist_ok=True)
    befehl = befehl_bauen(stand.programm, projekt, zielordner, stufe,
                          grundpaket)
    logger.info("SDK-Bau: %s", " ".join(befehl))
    if melden is not None:
        melden("[SDK] " + " ".join(befehl))

    anlauf: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "cwd": os.path.dirname(stand.programm) or None,
        "creationflags": 0x08000000,   # CREATE_NO_WINDOW
    }

    zeilen: "list[str]" = []
    abgelaufen = threading.Event()
    try:
        with subprocess.Popen(befehl, **anlauf) as lauf:
            if prozess_ablage is not None:
                prozess_ablage["prozess"] = lauf

            def _zeit_ist_um() -> None:
                abgelaufen.set()
                try:
                    lauf.kill()
                except Exception:  # noqa: BLE001
                    pass

            wecker = threading.Timer(float(zeitgrenze), _zeit_ist_um)
            wecker.daemon = True
            wecker.start()
            try:
                for zeile in lauf.stdout or ():
                    text = zeile.rstrip("\n")
                    zeilen.append(text)
                    if melden is not None:
                        melden(text)
                rueckgabe = lauf.wait()
            finally:
                wecker.cancel()
    except OSError as fehler:
        raise SdkFehler("%s nicht startbar: %s"
                        % (stand.programm, fehler)) from fehler

    if abgelaufen.is_set():
        raise SdkFehler("Zeitgrenze von %.0f s erreicht." % zeitgrenze)
    return rueckgabe, zeilen
