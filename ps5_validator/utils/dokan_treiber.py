# -*- coding: utf-8 -*-
"""Ist Dokan 2 wirklich einsatzbereit - oder liegen nur Teile davon da?

Unter Windows lesen, pruefen und entpacken die ``.ffpkg``-Wege ueber ein
Dokan-Laufwerk (UFS2Tool ``mount_udf``). Dafuer braucht es **Dokan 2**: den
Kerneltreiber ``dokan2.sys`` und die Laufzeit ``dokan2.dll``, die nur mit
ihm spricht. Ein Treiber aus Dokan 1 (``dokan1.sys``, ``dokan.sys``) hilft
ihr nicht.

Bis v1.9.28 liess ``_find_dokan_driver`` einen Dokan-1-Treiber neben einer
``dokan2.dll`` gelten, und der Diagnosebericht nannte Dokan gar nicht. Hier
steht beides an einer Stelle: die Dateipruefung, die das Programm vor dem
Einhaengen braucht (:func:`dateien_bereit`), und das Urteil samt Dienst fuer
den Bericht (:func:`zustand`). So koennen die beiden nicht auseinanderlaufen.

Gemessen am 19.09.2026 auf dem Entwicklungsrechner: Dokan Library 2.3.1.1000
legt ``System32\\drivers\\dokan2.sys`` und ``System32\\dokan2.dll`` ab und
traegt den Dienst ``dokan2`` mit Start=2 ein; keiner der alten Treiber liegt
dort.

Alles hier **liest nur**: Dateisystem, Registry und - wie schon zuvor in
``_find_dokan_driver`` - ein Ladeversuch der DLL, falls sie nicht in System32
liegt. Installiert oder geaendert wird nichts.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

#: Der Dienst, den Dokan 2 fuer seinen Treiber eintraegt.
DIENST = "dokan2"
#: Der Treiber, mit dem ``dokan2.dll`` spricht.
TREIBER = "dokan2.sys"
#: Die Laufzeit von Dokan 2.
LAUFZEIT = "dokan2.dll"
#: Treiber aus Dokan 1 - fuer ``dokan2.dll`` wertlos.
ALTE_TREIBER = ("dokan1.sys", "dokan.sys")
#: ``Start`` = 4 heisst: Dienst deaktiviert.
START_DEAKTIVIERT = 4

# Die Urteile, vom guenstigsten zum schlechtesten gelesen.
BEREIT = "bereit"
NICHT_WINDOWS = "nicht_windows"
NICHT_INSTALLIERT = "nicht_installiert"
NUR_DOKAN1 = "nur_dokan1"
TREIBER_FEHLT = "treiber_fehlt"
LAUFZEIT_FEHLT = "laufzeit_fehlt"
DIENST_FEHLT = "dienst_fehlt"
DEAKTIVIERT = "deaktiviert"
UNBEKANNT = "unbekannt"


@dataclass
class Dokanzustand:
    """Was ueber Dokan feststeht.

    ``treiber`` nennt die vorhandenen Treiberdateien, auch alte;
    ``dienst_start`` ist ``None``, wenn der Dienst nicht eingetragen ist.
    """

    urteil: str
    treiber: tuple[str, ...] = ()
    laufzeit: bool = False
    dienst_start: int | None = None
    hinweise: list[str] = field(default_factory=list)


@dataclass
class Messfuehler:
    """Die Stellen, an denen gelesen wird - fuer Pruefungen ersetzbar."""

    treiberdateien: Callable[[], "tuple[str, ...]"]
    laufzeit_im_system: Callable[[], bool]
    laufzeit_ladbar: Callable[[], bool]
    dienst_start: Callable[[], "int | None"]


def _system32() -> str:
    """Zur Laufzeit gelesen, nicht beim Import - Pruefungen lenken es um."""
    return os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32")


def laufzeit_pfad() -> str:
    """Wo ``dokan2.dll`` bei einer gewoehnlichen Installation liegt."""
    return os.path.join(_system32(), LAUFZEIT)


def _treiberdateien_lesen() -> tuple[str, ...]:
    ordner = os.path.join(_system32(), "drivers")
    return tuple(name for name in (TREIBER,) + ALTE_TREIBER
                 if os.path.isfile(os.path.join(ordner, name)))


def _laufzeit_im_system_lesen() -> bool:
    return os.path.isfile(laufzeit_pfad())


def _laufzeit_ladbar_lesen() -> bool:
    """Laesst sich ``dokan2.dll`` aus dem Suchpfad laden?

    Der Ladeversuch stammt aus dem frueheren ``_find_dokan_driver`` und
    bleibt der Rueckfall, wenn die DLL nicht in System32 liegt. ``ctypes``
    wird hier geholt, nicht beim Import - Pruefungen ersetzen ``WinDLL``.
    """
    try:
        import ctypes  # noqa: PLC0415

        ctypes.WinDLL(LAUFZEIT)
    except Exception:  # noqa: BLE001 - jedes Scheitern heisst "nicht ladbar"
        return False
    return True


def _dienst_start_lesen() -> "int | None":
    """``Start`` des Dienstes dokan2; None, wenn es den Dienst nicht gibt."""
    import winreg  # noqa: PLC0415 - nur unter Windows vorhanden

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\%s" % DIENST) as schluessel:
            wert, _typ = winreg.QueryValueEx(schluessel, "Start")
            return int(wert)
    except FileNotFoundError:
        return None


def echte_messfuehler() -> Messfuehler:
    return Messfuehler(treiberdateien=_treiberdateien_lesen,
                       laufzeit_im_system=_laufzeit_im_system_lesen,
                       laufzeit_ladbar=_laufzeit_ladbar_lesen,
                       dienst_start=_dienst_start_lesen)


def _laufzeit_da(fuehler: Messfuehler) -> bool:
    # Erst die Datei, dann der Ladeversuch: Er laedt die DLL in den Prozess
    # und soll nur laufen, wenn es ohne ihn nicht geht.
    return bool(fuehler.laufzeit_im_system()) or bool(fuehler.laufzeit_ladbar())


def dateien_bereit(fuehler: "Messfuehler | None" = None) -> bool:
    """Treiber und Laufzeit von Dokan 2 - die Pruefung vor dem Einhaengen.

    Das ist, was ``_find_dokan_driver`` seit v1.9.28 prueft. Der Dienst
    bleibt hier aussen vor; ihn nennt :func:`zustand` im Bericht.
    """
    fuehler = fuehler or echte_messfuehler()
    return TREIBER in tuple(fuehler.treiberdateien()) and _laufzeit_da(fuehler)


def zustand(fuehler: "Messfuehler | None" = None, *,
            windows: "bool | None" = None) -> Dokanzustand:
    """Beurteilt Dokan samt Dienst.

    Args:
        fuehler: Die Lesestellen; ohne Angabe die echten.
        windows: Nur fuer Pruefungen; sonst entscheidet ``sys.platform`` -
            dasselbe Merkmal wie in ``_find_dokan_driver``.
    """
    if not (sys.platform.startswith("win") if windows is None else windows):
        return Dokanzustand(NICHT_WINDOWS)
    fuehler = fuehler or echte_messfuehler()
    ergebnis = Dokanzustand(UNBEKANNT)
    try:
        ergebnis.treiber = tuple(fuehler.treiberdateien())
        ergebnis.laufzeit = _laufzeit_da(fuehler)
        ergebnis.dienst_start = fuehler.dienst_start()
    except Exception as exc:  # noqa: BLE001 - ein Bericht darf daran nicht scheitern
        logger.debug("Dokan nicht pruefbar: %s", exc)
        ergebnis.hinweise.append(str(exc))
        return ergebnis

    hat_treiber = TREIBER in ergebnis.treiber
    alte = [name for name in ergebnis.treiber if name in ALTE_TREIBER]
    if not hat_treiber and not ergebnis.laufzeit:
        ergebnis.urteil = NUR_DOKAN1 if alte else NICHT_INSTALLIERT
    elif not hat_treiber:
        ergebnis.urteil = TREIBER_FEHLT
    elif not ergebnis.laufzeit:
        ergebnis.urteil = LAUFZEIT_FEHLT
    elif ergebnis.dienst_start is None:
        ergebnis.urteil = DIENST_FEHLT
    elif ergebnis.dienst_start == START_DEAKTIVIERT:
        ergebnis.urteil = DEAKTIVIERT
    else:
        ergebnis.urteil = BEREIT
    return ergebnis


def berichtszeile(z: Dokanzustand, fassung: str = "") -> str:
    """Der Text fuer den Diagnosebericht - leer, wo es nichts zu sagen gibt.

    Wo die Dateien fehlen, hilft der Knopf des Programms. Wo sie da sind,
    der Dienst aber nicht, hilft er nicht: Er prueft dieselben Dateien, haelt
    Dokan fuer installiert und tut nichts - dann bleibt nur, Dokan neu zu
    installieren.
    """
    knopf = ("Abhilfe: im Fenster „Ressourcen & nützliche Links“ auf "
             "„Dokan2-Treiber installieren“.")
    neu = "Abhilfe: Dokan Library über die Windows-Einstellungen neu installieren."
    alte = ", ".join(name for name in z.treiber if name in ALTE_TREIBER)
    if z.urteil == NICHT_WINDOWS:
        return ""
    if z.urteil == BEREIT:
        return "bereit (%s, %s, Dienst %s Start=%s%s)" % (
            TREIBER, LAUFZEIT, DIENST, z.dienst_start,
            ", Fassung %s" % fassung if fassung else "")
    if z.urteil == NICHT_INSTALLIERT:
        return ("nicht installiert – gebraucht nur unter Windows, um .ffpkg über "
                "ein Dokan-Laufwerk zu lesen, zu prüfen und zu entpacken. " + knopf)
    if z.urteil == NUR_DOKAN1:
        return ("nur Dokan 1 (%s) – das Programm braucht Dokan 2, der alte "
                "Treiber hilft ihm nicht. %s" % (alte, knopf))
    if z.urteil == TREIBER_FEHLT:
        return ("UNVOLLSTÄNDIG – %s ist da, der Treiber %s fehlt%s. %s" % (
            LAUFZEIT, TREIBER,
            " (%s gehört zu Dokan 1)" % alte if alte else "", knopf))
    if z.urteil == LAUFZEIT_FEHLT:
        return ("UNVOLLSTÄNDIG – %s ist da, die Laufzeit %s fehlt. %s" % (
            TREIBER, LAUFZEIT, knopf))
    if z.urteil == DIENST_FEHLT:
        return ("UNVOLLSTÄNDIG – %s und %s sind da, der Dienst %s ist aber nicht "
                "eingetragen; so lädt Windows den Treiber nicht. %s" % (
                    TREIBER, LAUFZEIT, DIENST, neu))
    if z.urteil == DEAKTIVIERT:
        return ("DEAKTIVIERT – der Dienst %s steht auf Start=4; so lädt Windows "
                "den Treiber nicht. %s" % (DIENST, neu))
    grund = "; ".join(z.hinweise) if z.hinweise else "Zustand nicht lesbar"
    return "nicht feststellbar (%s)" % grund
