# -*- coding: utf-8 -*-
"""Eine Homebrew-App aus ihrem Release-ZIP auf die PS5 bringen - ohne Entpacken.

Wunsch des Nutzers vom 26.09.2026 fuer ProsperoEden (Switch-Emulator,
github.com/blackbearreloaded/ProsperoEden): Dessen Release-ZIP enthaelt genau
einen App-Ordner (``PPSA99008/`` mit ``eboot.bin`` und ``sce_sys/param.json``),
der laut README nach ``/data/homebrew/PPSA99008`` gehoert. Von dort liest
ShadowMount+ ihn ein wie jeden Dump-Ordner.

Die Dateien gehen **direkt aus dem ZIP** ueber FTP auf die Konsole - auf dem
PC wird nichts entpackt. Damit gibt es dort auch keinen Weg, auf dem ein
praepariertes Archiv etwas ausserhalb eines Zielordners ablegen koennte
("Zip Slip"). Auf der Konsole landet nur, was unter dem App-Ordner steht,
und jeder Pfad im Archiv wird vorher geprueft - ein einziger unzulaessiger
Pfad verwirft das ganze Paket.

**Nichts wird geloescht.** Vorhandene Dateien der App werden ersetzt (so
aktualisiert man laut README), alles andere im Ordner bleibt - bei
ProsperoEden die eigenen Dateien des Anwenders unter ``assets/``. Abgebrochen
wird nur zwischen zwei Dateien (Regel aus :mod:`konsole_ftp`).

Mitgeliefert wird nichts: Das ZIP waehlt der Anwender. Das Programm legt fuer
eine App hoechstens **leere** Ordner an, die sie fuer die eigenen Dateien des
Anwenders erwartet (:data:`ZUSATZORDNER`) - nie deren Inhalt.

Nur Standardbibliothek; keine Oberflaeche. Fehler kommen als
:class:`PaketFehler` mit Textschluessel, damit die Oberflaeche sie in der
gewaehlten Sprache zeigt.
"""
from __future__ import annotations

import ftplib
import json
import posixpath
import re
import zipfile
from dataclasses import dataclass
from typing import Callable

from ps5_validator.utils import konsole_ftp

#: Wo Homebrew-Apps auf der Konsole liegen - dort liest ShadowMount+ sie ein.
ZIEL_BASIS = "/data/homebrew"

#: Ein App-Ordner heisst wie eine Title-ID: vier Grossbuchstaben, fuenf Ziffern.
_ORDNER_RE = re.compile(r"^[A-Z]{4}\d{5}$")

#: Leere Ordner, die eine App fuer die eigenen Dateien des Anwenders erwartet.
#: ProsperoEden (README v1.000.010): Schluessel unter ``assets/keys``,
#: Firmware unter ``assets/firmware``, Spiele unter ``assets/roms``.
ZUSATZORDNER: dict[str, tuple[str, ...]] = {
    "PPSA99008": ("assets/keys", "assets/firmware", "assets/roms"),
}

#: Dateityp "symbolische Verknuepfung" in den Unix-Rechten eines ZIP-Eintrags.
_S_IFMT, _S_IFLNK = 0o170000, 0o120000


class PaketFehler(Exception):
    """Das ZIP taugt nicht als App-Paket.

    ``schluessel`` ist ein Textschluessel (``apppaket.grund_*``), ``werte``
    sind seine Platzhalter.
    """

    def __init__(self, schluessel: str, **werte) -> None:
        super().__init__(schluessel)
        self.schluessel = schluessel
        self.werte = werte


@dataclass(frozen=True)
class Datei:
    """Eine Datei der App im Archiv."""

    im_zip: str
    relativ: str
    groesse: int


@dataclass(frozen=True)
class AppPaket:
    """Was in einem App-ZIP steckt - gelesen, ohne etwas zu entpacken."""

    zip_pfad: str
    kennung: str
    titel: str
    fassung: str
    dateien: tuple[Datei, ...]

    @property
    def bytes_gesamt(self) -> int:
        return sum(d.groesse for d in self.dateien)

    @property
    def ziel(self) -> str:
        """Der App-Ordner auf der Konsole."""
        return posixpath.join(ZIEL_BASIS, self.kennung)

    @property
    def zusatzordner(self) -> tuple[str, ...]:
        return ZUSATZORDNER.get(self.kennung, ())


def _pfad_sicher(name: str) -> bool:
    """Darf dieser Name aus dem Archiv auf die Konsole? Nur schlichte relative Pfade."""
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name:
        return False
    if any(ord(zeichen) < 32 for zeichen in name):
        return False
    return all(teil not in ("..", ".") for teil in name.split("/"))


def _titel_aus_param(daten: dict) -> str:
    """Der Name der App - wie das Menue der Konsole ihn zeigt."""
    name = str(daten.get("titleName", "") or "").strip()
    if name:
        return name
    ortsteil = daten.get("localizedParameters") or {}
    if isinstance(ortsteil, dict):
        vorgabe = str(ortsteil.get("defaultLanguage", "en-US") or "en-US")
        for sprache in (vorgabe, "en-US", "de-DE"):
            block = ortsteil.get(sprache) or {}
            if isinstance(block, dict):
                name = str(block.get("titleName", "") or "").strip()
                if name:
                    return name
    return ""


def paket_lesen(zip_pfad: str) -> AppPaket:
    """Liest ein App-ZIP und prueft es - ohne etwas zu entpacken.

    Der App-Ordner darf oben im Archiv liegen (``PPSA99008/...``) oder eine
    Ebene tiefer (``ProsperoEden-v1.000.010/PPSA99008/...``). Erwartet werden
    ``eboot.bin`` und ``sce_sys/param.json``; die Title-ID der ``param.json``
    muss der Ordnername sein.

    Raises:
        PaketFehler: kein lesbares ZIP, unzulaessiger Pfad oder symbolische
            Verknuepfung im Archiv, kein oder mehr als ein App-Ordner, keine
            lesbare ``param.json`` oder eine andere Kennung darin.
    """
    try:
        archiv = zipfile.ZipFile(zip_pfad)
    except (OSError, zipfile.BadZipFile) as fehler:
        raise PaketFehler("apppaket.grund_kein_zip", fehler=fehler) from fehler
    with archiv:
        eintraege = [e for e in archiv.infolist() if not e.is_dir()]
        for eintrag in archiv.infolist():
            if not _pfad_sicher(eintrag.filename):
                raise PaketFehler("apppaket.grund_unsicherer_pfad", pfad=eintrag.filename)
            if (eintrag.external_attr >> 16) & _S_IFMT == _S_IFLNK:
                raise PaketFehler("apppaket.grund_unsicherer_pfad", pfad=eintrag.filename)

        namen = {e.filename for e in eintraege}
        kandidaten = sorted({
            name[:-len("eboot.bin")] for name in namen
            if name.endswith("eboot.bin")
            and name.count("/") in (1, 2)
            and _ORDNER_RE.match(name.split("/")[-2])
            and name[:-len("eboot.bin")] + "sce_sys/param.json" in namen})
        if not kandidaten:
            raise PaketFehler("apppaket.grund_kein_ordner")
        if len(kandidaten) > 1:
            raise PaketFehler("apppaket.grund_mehrere",
                              ordner=", ".join(k.rstrip("/") for k in kandidaten))
        praefix = kandidaten[0]
        kennung = praefix.rstrip("/").split("/")[-1]

        try:
            daten = json.loads(archiv.read(praefix + "sce_sys/param.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError, KeyError, zipfile.BadZipFile) as fehler:
            raise PaketFehler("apppaket.grund_param", fehler=fehler) from fehler
        if not isinstance(daten, dict):
            raise PaketFehler("apppaket.grund_param", fehler=type(daten).__name__)
        angegeben = str(daten.get("titleId", "") or "").strip().upper()
        if angegeben and angegeben != kennung:
            raise PaketFehler("apppaket.grund_kennung", ordner=kennung, kennung=angegeben)

        dateien = tuple(
            Datei(im_zip=e.filename, relativ=e.filename[len(praefix):], groesse=e.file_size)
            for e in sorted(eintraege, key=lambda e: e.filename)
            if e.filename.startswith(praefix))
    return AppPaket(zip_pfad=str(zip_pfad), kennung=kennung,
                    titel=_titel_aus_param(daten) or kennung,
                    fassung=str(daten.get("contentVersion", "") or "").strip(),
                    dateien=dateien)


def senden(adresse: str, paket: AppPaket, port: int = konsole_ftp.FTP_PORT,
           auf_fortschritt: "Callable[[konsole_ftp.Fortschritt], None] | None" = None,
           abbruch: "Callable[[], bool] | None" = None) -> konsole_ftp.Fortschritt:
    """Schickt die Dateien der App aus dem ZIP nach :attr:`AppPaket.ziel`.

    Jeder Ordner wird einmal angelegt (``MKD``, Vorhandenes stoert nicht),
    jede Datei mit einem ``STOR`` direkt aus dem Archiv geschrieben. Nichts
    wird geloescht. ``abbruch`` wird **vor** jeder Datei gefragt, nie
    mittendrin; nach einem Abbruch werden auch keine :data:`ZUSATZORDNER`
    mehr angelegt.

    Returns:
        Den Endstand; ``abgebrochen`` sagt, ob die App vollstaendig ist.

    Raises:
        konsole_ftp.FtpFehler: keine Verbindung, oder eine Datei liess sich
            nicht schreiben.
    """
    stand = konsole_ftp.Fortschritt(dateien_gesamt=len(paket.dateien),
                                    bytes_gesamt=paket.bytes_gesamt)
    verbindung = konsole_ftp.verbinden(adresse, port)
    verbindung.timeout = konsole_ftp.DATEN_ZEIT
    angelegt: set[str] = set()

    def _ordner(pfad: str) -> None:
        teil = ""
        for stueck in pfad.strip("/").split("/"):
            teil = "%s/%s" % (teil, stueck)
            if teil in angelegt:
                continue
            try:
                verbindung.mkd(teil)
            except ftplib.error_perm:
                pass                 # gibt es schon
            angelegt.add(teil)

    def _melden() -> None:
        if auf_fortschritt is not None:
            auf_fortschritt(stand)

    def _gelesen(block: bytes) -> None:
        stand.bytes += len(block)
        _melden()

    try:
        with zipfile.ZipFile(paket.zip_pfad) as archiv:
            for datei in paket.dateien:
                if abbruch is not None and abbruch():
                    stand.abgebrochen = True
                    break
                zielpfad = posixpath.join(paket.ziel, datei.relativ)
                _ordner(posixpath.dirname(zielpfad))
                stand.aktuell = datei.relativ
                _melden()
                try:
                    with archiv.open(datei.im_zip) as eingabe:
                        verbindung.storbinary("STOR %s" % zielpfad, eingabe,
                                              callback=_gelesen)
                except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
                    raise konsole_ftp.FtpFehler(
                        "%s nicht schreibbar: %s" % (datei.relativ, fehler)) from fehler
                stand.dateien += 1
                _melden()
            if not stand.abgebrochen:
                for ordner in paket.zusatzordner:
                    _ordner(posixpath.join(paket.ziel, ordner))
        return stand
    finally:
        konsole_ftp.schliessen(verbindung)
