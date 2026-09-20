# -*- coding: utf-8 -*-
"""Einen Treiber fuer ein virtuelles Geraet einrichten - wie ``devcon install``.

OSFMount braucht seinen Treiber ``osfdisk`` fuer ein Geraet, das es nicht von
selbst gibt: ``root\\osfdisk``, einen virtuellen SCSI-Adapter. Gemessen am
19.09.2026 auf dem Entwicklungsrechner: OSFMount 3.3.1000 samt
``win10\\osfdisk.inf`` lag da, aber weder Dienst noch Treiberpaket noch
Geraet (siehe ``osfmount_treiber``).

``pnputil /add-driver <inf> /install`` genuegt dafuer nicht - so riet es der
Diagnosebericht bis v1.9.29. Es legt das Paket in den Treiberspeicher und
installiert es auf *vorhandene* passende Geraete. Ein virtuelles Geraet muss
erst angelegt werden, und dafuer hat pnputil keinen Befehl (``pnputil /?``
auf Windows 11 Build 26200 gelesen).

Der Ablauf ist der von ``devcon update`` und ``devcon install``:

1. ``UpdateDriverForPlugAndPlayDevicesW`` mit der Hardware-ID. Gibt es das
   Geraet schon - auch ohne Treiber -, ist der Treiber damit eingerichtet.
2. Meldet Windows "kein passendes Geraet" (``ERROR_NO_SUCH_DEVINST``): das
   Geraet anlegen. Die Geraeteklasse kommt aus der INF
   (``SetupDiGetINFClassW``), dann ``SetupDiCreateDeviceInfoW`` mit
   ``DICD_GENERATE_ID``, die Hardware-ID als ``REG_MULTI_SZ`` und
   ``DIF_REGISTERDEVICE``. Danach Schritt 1 noch einmal.
3. Scheitert Schritt 1 danach, wird das eben angelegte Geraet wieder
   entfernt (``DIF_REMOVE``): kein verwaistes Geraet ohne Treiber.

Erst nachsehen, dann anlegen - so entsteht nie ein zweites ``root\\osfdisk``,
auch wenn die Registry sich einmal nicht lesen laesst.

Windows fragt beim ersten Treiber eines Herstellers womoeglich nach, ob die
Geraetesoftware installiert werden soll. Alles hier braucht
Administratorrechte; der Aufrufer prueft sie vorher. Dieses Modul uebersetzt
nichts: Es liefert Schritt und Fehlercode, den Satz dazu baut die Oberflaeche.
"""
from __future__ import annotations

import ctypes
import logging
import os
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

#: Wo es scheitern kann - der Aufrufer macht daraus einen Satz.
NICHT_WINDOWS = "nicht_windows"
INF_FEHLT = "inf_fehlt"
#: Gar nicht erst versucht: ohne Administratorrechte (setzt der Aufrufer).
KEINE_RECHTE = "keine_rechte"
SCHRITT_KLASSE = "klasse"      # SetupDiGetINFClassW
SCHRITT_GERAET = "geraet"      # anlegen und registrieren
SCHRITT_TREIBER = "treiber"    # UpdateDriverForPlugAndPlayDevicesW

ERROR_ACCESS_DENIED = 5
ERROR_CANCELLED = 1223
# SetupAPI-Fehler (setupapi.h): APPLICATION_ERROR_MASK | ERROR_SEVERITY_ERROR | n
ERROR_NO_SUCH_DEVINST = 0xE000020B
ERROR_IN_WOW64 = 0xE0000235
ERROR_DRIVER_STORE_ADD_FAILED = 0xE0000247
ERROR_DEVICE_INSTALL_BLOCKED = 0xE0000248
ERROR_DRIVER_INSTALL_BLOCKED = 0xE0000249
ERROR_FILE_HASH_NOT_IN_CATALOG = 0xE000024B

#: Fehler mit eigenem Satz in der Oberflaeche. Fuer die SetupAPI-Codes
#: (0xE000....) liefert FormatMessage keinen Text - gemessen am 19.09.2026:
#: "<no description>".
BEKANNTE_FEHLER = {
    ERROR_ACCESS_DENIED: "rechte",
    ERROR_CANCELLED: "abgebrochen",
    ERROR_IN_WOW64: "wow64",
    ERROR_DRIVER_STORE_ADD_FAILED: "treiberspeicher",
    ERROR_DEVICE_INSTALL_BLOCKED: "blockiert",
    ERROR_DRIVER_INSTALL_BLOCKED: "blockiert",
    ERROR_FILE_HASH_NOT_IN_CATALOG: "signatur",
}

DICD_GENERATE_ID = 0x1
DIF_REMOVE = 0x05
DIF_REGISTERDEVICE = 0x19
SPDRP_HARDWAREID = 0x1
INSTALLFLAG_FORCE = 0x1
MAX_CLASS_NAME_LEN = 32


class WindowsFehler(Exception):
    """Ein Aufruf nach Windows ist gescheitert - mit Schritt und Fehlercode."""

    def __init__(self, schritt: str, code: int) -> None:
        self.schritt = schritt
        self.code = int(code) & 0xFFFFFFFF
        super().__init__("%s: 0x%08X" % (schritt, self.code))


@dataclass
class Ergebnis:
    """Was beim Einrichten herauskam."""

    ok: bool
    schritt: str = ""
    code: int = 0
    neustart: bool = False
    #: Das Geraet gab es vorher nicht, es wurde angelegt.
    geraet_angelegt: bool = False
    #: Ein angelegtes Geraet wurde nach einem Fehlschlag wieder entfernt.
    entfernt: bool = False


class Schnittstelle(Protocol):
    """Die Aufrufe nach Windows - fuer Pruefungen austauschbar."""

    def treiber_installieren(self, hardware_id: str, inf: str) -> bool: ...
    def geraet_anlegen(self, inf: str, hardware_id: str) -> object: ...
    def geraet_entfernen(self, geraet: object) -> None: ...
    def freigeben(self, geraet: object) -> None: ...


def hardware_id_multi_sz(hardware_id: str) -> bytes:
    """Die Hardware-ID als ``REG_MULTI_SZ``: UTF-16, doppelt abgeschlossen."""
    return (hardware_id + "\0\0").encode("utf-16-le")


def systemtext(code: int) -> str:
    """Der Text, den Windows selbst zu einem Fehlercode kennt - sonst leer."""
    if os.name != "nt":
        return ""
    wert = int(code) & 0xFFFFFFFF
    if wert >= 0x80000000:
        wert -= 1 << 32
    text = ctypes.FormatError(wert).strip()
    return "" if text.startswith("<") else text


def einrichten(inf: str, hardware_id: str, *, api: "Schnittstelle | None" = None,
               windows: "bool | None" = None) -> Ergebnis:
    """Richtet den Treiber aus ``inf`` fuer das Geraet ``hardware_id`` ein.

    Legt das Geraet an, wenn es fehlt (siehe Moduldoku). Braucht
    Administratorrechte.

    Args:
        inf: Die INF-Datei des Treibers.
        hardware_id: Etwa ``root\\osfdisk``.
        api: Die Aufrufe nach Windows; ohne Angabe die echten.
        windows: Nur fuer Pruefungen; sonst entscheidet ``os.name``.
    """
    if not (os.name == "nt" if windows is None else windows):
        return Ergebnis(False, NICHT_WINDOWS)
    if not inf or not os.path.isfile(inf):
        return Ergebnis(False, INF_FEHLT)
    inf = os.path.abspath(inf)
    api = api if api is not None else SetupApi()
    try:
        return Ergebnis(True, neustart=bool(api.treiber_installieren(hardware_id, inf)))
    except WindowsFehler as exc:
        if exc.code != ERROR_NO_SUCH_DEVINST:
            return Ergebnis(False, exc.schritt, exc.code)
    # Kein Geraet mit dieser Hardware-ID: anlegen, dann noch einmal.
    try:
        geraet = api.geraet_anlegen(inf, hardware_id)
    except WindowsFehler as exc:
        return Ergebnis(False, exc.schritt, exc.code)
    try:
        neustart = bool(api.treiber_installieren(hardware_id, inf))
        return Ergebnis(True, neustart=neustart, geraet_angelegt=True)
    except WindowsFehler as exc:
        entfernt = False
        try:
            api.geraet_entfernen(geraet)
            entfernt = True
        except WindowsFehler as weg:
            logger.warning("Angelegtes Geraet %s liess sich nicht entfernen: %s",
                           hardware_id, weg)
        return Ergebnis(False, exc.schritt, exc.code, geraet_angelegt=True,
                        entfernt=entfernt)
    finally:
        api.freigeben(geraet)


# --- die echten Aufrufe ------------------------------------------------------

class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _SP_DEVINFO_DATA(ctypes.Structure):
    """SP_DEVINFO_DATA: 32 Byte unter 64 Bit, 28 unter 32 Bit (``cbSize``)."""

    _fields_ = [("cbSize", ctypes.c_uint32), ("ClassGuid", _GUID),
                ("DevInst", ctypes.c_uint32), ("Reserved", ctypes.c_size_t)]


def guid_text(guid: _GUID) -> str:
    """``{4D36E97B-E325-11CE-BFC1-08002BE10318}``-Schreibweise."""
    rest = bytes(guid.Data4)
    return "{%08X-%04X-%04X-%s-%s}" % (guid.Data1, guid.Data2, guid.Data3,
                                       rest[:2].hex().upper(), rest[2:].hex().upper())


@dataclass
class _Angelegt:
    liste: int
    daten: _SP_DEVINFO_DATA


class SetupApi:
    """setupapi.dll und newdev.dll ueber ctypes - nur unter Windows."""

    def __init__(self) -> None:
        from ctypes import wintypes as wt  # noqa: PLC0415 - nur unter Windows

        self._wt = wt
        self._setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
        self._newdev = ctypes.WinDLL("newdev", use_last_error=True)
        s = self._setupapi
        s.SetupDiGetINFClassW.argtypes = [wt.LPCWSTR, ctypes.POINTER(_GUID), wt.LPWSTR,
                                          wt.DWORD, ctypes.POINTER(wt.DWORD)]
        s.SetupDiGetINFClassW.restype = wt.BOOL
        s.SetupDiCreateDeviceInfoList.argtypes = [ctypes.POINTER(_GUID), wt.HWND]
        s.SetupDiCreateDeviceInfoList.restype = ctypes.c_void_p
        s.SetupDiCreateDeviceInfoW.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(_GUID),
                                               wt.LPCWSTR, wt.HWND, wt.DWORD,
                                               ctypes.POINTER(_SP_DEVINFO_DATA)]
        s.SetupDiCreateDeviceInfoW.restype = wt.BOOL
        s.SetupDiSetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p,
                                                        ctypes.POINTER(_SP_DEVINFO_DATA),
                                                        wt.DWORD, ctypes.c_void_p, wt.DWORD]
        s.SetupDiSetDeviceRegistryPropertyW.restype = wt.BOOL
        s.SetupDiCallClassInstaller.argtypes = [wt.DWORD, ctypes.c_void_p,
                                                ctypes.POINTER(_SP_DEVINFO_DATA)]
        s.SetupDiCallClassInstaller.restype = wt.BOOL
        s.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        s.SetupDiDestroyDeviceInfoList.restype = wt.BOOL
        n = self._newdev
        n.UpdateDriverForPlugAndPlayDevicesW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR,
                                                         wt.DWORD, ctypes.POINTER(wt.BOOL)]
        n.UpdateDriverForPlugAndPlayDevicesW.restype = wt.BOOL

    @staticmethod
    def _fehler(schritt: str) -> WindowsFehler:
        return WindowsFehler(schritt, ctypes.get_last_error())

    def inf_klasse(self, inf: str) -> "tuple[_GUID, str]":
        """Geraeteklasse der INF - liest nur."""
        guid = _GUID()
        name = ctypes.create_unicode_buffer(MAX_CLASS_NAME_LEN)
        noetig = self._wt.DWORD()
        if not self._setupapi.SetupDiGetINFClassW(inf, ctypes.byref(guid), name,
                                                  MAX_CLASS_NAME_LEN, ctypes.byref(noetig)):
            raise self._fehler(SCHRITT_KLASSE)
        return guid, name.value

    def geraet_anlegen(self, inf: str, hardware_id: str) -> _Angelegt:
        guid, klasse = self.inf_klasse(inf)
        s = self._setupapi
        liste = s.SetupDiCreateDeviceInfoList(ctypes.byref(guid), None)
        if not liste or liste == ctypes.c_void_p(-1).value:
            raise self._fehler(SCHRITT_GERAET)
        daten = _SP_DEVINFO_DATA()
        daten.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
        try:
            if not s.SetupDiCreateDeviceInfoW(liste, klasse, ctypes.byref(guid), None, None,
                                              DICD_GENERATE_ID, ctypes.byref(daten)):
                raise self._fehler(SCHRITT_GERAET)
            ids = hardware_id_multi_sz(hardware_id)
            puffer = ctypes.create_string_buffer(ids, len(ids))
            if not s.SetupDiSetDeviceRegistryPropertyW(liste, ctypes.byref(daten), SPDRP_HARDWAREID,
                                                       ctypes.cast(puffer, ctypes.c_void_p), len(ids)):
                raise self._fehler(SCHRITT_GERAET)
            if not s.SetupDiCallClassInstaller(DIF_REGISTERDEVICE, liste, ctypes.byref(daten)):
                raise self._fehler(SCHRITT_GERAET)
        except WindowsFehler:
            s.SetupDiDestroyDeviceInfoList(liste)
            raise
        return _Angelegt(liste, daten)

    def geraet_entfernen(self, geraet: _Angelegt) -> None:
        if not self._setupapi.SetupDiCallClassInstaller(DIF_REMOVE, geraet.liste,
                                                        ctypes.byref(geraet.daten)):
            raise self._fehler(SCHRITT_GERAET)

    def freigeben(self, geraet: _Angelegt) -> None:
        self._setupapi.SetupDiDestroyDeviceInfoList(geraet.liste)

    def treiber_installieren(self, hardware_id: str, inf: str) -> bool:
        """Treiber auf alle Geraete mit der Hardware-ID; True = Neustart noetig."""
        neustart = self._wt.BOOL(False)
        if not self._newdev.UpdateDriverForPlugAndPlayDevicesW(None, hardware_id, inf,
                                                               INSTALLFLAG_FORCE,
                                                               ctypes.byref(neustart)):
            raise self._fehler(SCHRITT_TREIBER)
        return bool(neustart.value)
