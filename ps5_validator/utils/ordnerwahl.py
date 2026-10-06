# -*- coding: utf-8 -*-
"""Mehrere Ordner in einem Dialog waehlen - der Ordnerdialog von Windows.

Wunsch des Nutzers vom 05.10.2026 zur Sammelkonvertierung (Aufgabe 5): mehrere
Dump-Ordner markieren und auf einmal uebernehmen. Tk kann das nicht:
``filedialog.askdirectory`` nimmt genau einen Ordner, und ``askopenfilenames``
zeigt nur Dateien. Windows hat den passenden Dialog seit Vista selbst - den
"Common Item Dialog" (``IFileOpenDialog``) mit ``FOS_PICKFOLDERS`` und
``FOS_ALLOWMULTISELECT``: Ordner mit Strg oder Umschalt markieren, dann
"Ordner auswaehlen". Tk benutzt denselben Dialog fuer ``askdirectory``, nur ohne
Mehrfachauswahl.

Angesprochen wird er hier ueber ``ctypes`` und die Methodentabellen der
COM-Schnittstellen - ohne weiteres Paket. Die Stellen in den Tabellen stehen in
``ShObjIdl_core.h`` des Windows SDK (``IModalWindow``, ``IFileDialog``,
``IFileOpenDialog``, ``IShellItem``, ``IShellItemArray``).

Unter Linux und macOS gibt es das nicht; :func:`ordner_waehlen` liefert dort
``None``, und der Aufrufer nimmt den Ordnerdialog von Tk (ein Ordner je Wahl).
Dasselbe gilt, wenn der Dialog unter Windows nicht anzulegen ist.

**Faden:** Der Dialog braucht einen Faden im Single-Threaded Apartment - den
Hauptfaden von Tk (Tk selbst richtet COM dort fuer seine eigenen Dialoge ein).
``Show`` ist modal und pumpt die Nachrichten selbst; die Fenster von Tk zeichnen
waehrenddessen weiter, wie bei jedem Dialog von Tk.

Dieses Modul bindet ``i18n`` nicht ein: Titel kommen vom Aufrufer.
"""
from __future__ import annotations

import ctypes
import logging
import os
import uuid

logger = logging.getLogger(__name__)

#: Klasse und Schnittstellen (ShObjIdl_core.h).
CLSID_FILEOPENDIALOG = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
IID_IFILEOPENDIALOG = "{D57C7288-D4AD-4768-BE02-9D969532D960}"
IID_ISHELLITEM = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"
IID_ISHELLITEMARRAY = "{B63EA76D-1F85-456F-A19C-48159EFA858B}"

#: Optionen des Dialogs (FILEOPENDIALOGOPTIONS).
FOS_NOCHANGEDIR = 0x00000008
FOS_PICKFOLDERS = 0x00000020
FOS_FORCEFILESYSTEM = 0x00000040
FOS_ALLOWMULTISELECT = 0x00000200
FOS_PATHMUSTEXIST = 0x00000800
#: Was der Ordnerdialog dieses Moduls immer setzt.
OPTIONEN = (FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_ALLOWMULTISELECT
            | FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR)

#: Der Pfad eines Eintrags im Dateisystem (SIGDN_FILESYSPATH).
SIGDN_FILESYSPATH = 0x80058000
CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2
#: "Abgebrochen" - HRESULT_FROM_WIN32(ERROR_CANCELLED).
HRESULT_ABGEBROCHEN = 0x800704C7
RPC_E_CHANGED_MODE = 0x80010106

#: Stellen in den Methodentabellen. IUnknown: 0 QueryInterface, 1 AddRef,
#: 2 Release. IModalWindow: 3 Show. IFileDialog ab 4 (SetFileTypes ...).
_RELEASE = 2
_SHOW = 3
_SET_OPTIONS = 9
_GET_OPTIONS = 10
_SET_FOLDER = 12
_GET_FOLDER = 13
_SET_TITLE = 17
_GET_RESULTS = 27            # IFileOpenDialog
_ITEM_GET_DISPLAY_NAME = 5   # IShellItem
_ARRAY_GET_COUNT = 7         # IShellItemArray
_ARRAY_GET_ITEM_AT = 8


class OrdnerwahlFehler(Exception):
    """Ein Aufruf an den Dialog scheiterte (HRESULT im Text)."""

    def __init__(self, was: str, hresult: int) -> None:
        self.hresult = hresult & 0xFFFFFFFF
        super().__init__("%s: HRESULT 0x%08X" % (was, self.hresult))


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    """Eine GUID aus ihrer Schreibweise - ohne COM-Aufruf (uuid kennt die Byte-Folge)."""
    return _GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


def verfuegbar() -> bool:
    """Gibt es den Dialog mit Mehrfachauswahl hier? Nur unter Windows."""
    return os.name == "nt"


#: Die Funktionen aus ole32 und shell32 - einmal je Prozess eingerichtet (:func:`_api`).
_API: dict = {}


def _api() -> dict:
    """Eigene Funktionszeiger mit festen Typen.

    Ueber eigene ``WinDLL``-Objekte, nicht ``ctypes.windll``: Dessen
    Funktionsobjekte teilt sich der ganze Prozess. Wer dort ``argtypes`` setzt,
    aendert sie fuer jeden anderen Aufrufer mit - ein fremder Aufruf mit einer
    anderen GUID-Struktur scheiterte danach mit ``ArgumentError``.
    """
    if not _API:
        ole32 = ctypes.WinDLL("ole32")
        shell32 = ctypes.WinDLL("shell32")
        zeiger = ctypes.POINTER(ctypes.c_void_p)
        guid = ctypes.POINTER(_GUID)
        for name, dll, argtypen, ergebnis in (
                ("CoInitializeEx", ole32, [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_long),
                ("CoUninitialize", ole32, [], None),
                ("CoTaskMemFree", ole32, [ctypes.c_void_p], None),
                ("CoCreateInstance", ole32,
                 [guid, ctypes.c_void_p, ctypes.c_uint32, guid, zeiger], ctypes.c_long),
                ("SHCreateItemFromParsingName", shell32,
                 [ctypes.c_wchar_p, ctypes.c_void_p, guid, zeiger], ctypes.c_long)):
            funktion = getattr(dll, name)
            funktion.argtypes = argtypen
            funktion.restype = ergebnis
            _API[name] = funktion
    return _API


def _methode(objekt: ctypes.c_void_p, stelle: int, *argtypen, ergebnis=ctypes.c_long):
    """Die Methode an ``stelle`` der Methodentabelle von ``objekt`` - aufrufbar mit ``objekt`` vorn."""
    tabelle = ctypes.cast(objekt, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototyp = ctypes.WINFUNCTYPE(ergebnis, ctypes.c_void_p, *argtypen)
    return prototyp(tabelle[stelle])


def _pruefen(hresult: int, was: str) -> None:
    if hresult < 0:
        raise OrdnerwahlFehler(was, hresult)


def _freigeben(objekt: ctypes.c_void_p) -> None:
    """``Release`` - ohne Wirkung bei einem leeren Zeiger."""
    if objekt and objekt.value:
        _methode(objekt, _RELEASE, ergebnis=ctypes.c_ulong)(objekt)
        objekt.value = None


def _anzeigename(eintrag: ctypes.c_void_p) -> str:
    """Der Dateisystempfad eines ``IShellItem`` - leer, wenn es keinen hat."""
    puffer = ctypes.c_void_p()
    hr = _methode(eintrag, _ITEM_GET_DISPLAY_NAME, ctypes.c_uint,
                  ctypes.POINTER(ctypes.c_void_p))(eintrag, SIGDN_FILESYSPATH,
                                                   ctypes.byref(puffer))
    if hr < 0 or not puffer.value:
        return ""
    try:
        return ctypes.wstring_at(puffer.value)
    finally:
        _api()["CoTaskMemFree"](puffer)


def pfade_aus_liste(liste: ctypes.c_void_p) -> list[str]:
    """Die Pfade aller Eintraege eines ``IShellItemArray``, in seiner Reihenfolge.

    Eintraege ohne Dateisystempfad (etwa "Dieser PC") fallen heraus; der Dialog
    laesst sie mit ``FOS_FORCEFILESYSTEM`` gar nicht erst zu.
    """
    anzahl = ctypes.c_uint32()
    _pruefen(_methode(liste, _ARRAY_GET_COUNT, ctypes.POINTER(ctypes.c_uint32))(
        liste, ctypes.byref(anzahl)), "IShellItemArray.GetCount")
    pfade: list[str] = []
    hole = _methode(liste, _ARRAY_GET_ITEM_AT, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))
    for stelle in range(anzahl.value):
        eintrag = ctypes.c_void_p()
        _pruefen(hole(liste, stelle, ctypes.byref(eintrag)), "IShellItemArray.GetItemAt")
        try:
            pfad = _anzeigename(eintrag)
        finally:
            _freigeben(eintrag)
        if pfad:
            pfade.append(pfad)
    return pfade


def eintrag_zu_pfad(pfad: str) -> ctypes.c_void_p:
    """Ein ``IShellItem`` fuer einen Pfad (``SHCreateItemFromParsingName``) - der Aufrufer gibt es frei."""
    eintrag = ctypes.c_void_p()
    iid = _guid(IID_ISHELLITEM)
    _pruefen(_api()["SHCreateItemFromParsingName"](pfad, None, ctypes.byref(iid),
                                                   ctypes.byref(eintrag)),
             "SHCreateItemFromParsingName")
    return eintrag


def dialog_anlegen(titel: str = "", startordner: str = "") -> ctypes.c_void_p:
    """Legt den Ordnerdialog an und richtet ihn ein - ohne ihn zu zeigen.

    Getrennt von :func:`ordner_waehlen`, damit sich das Einrichten pruefen
    laesst, ohne dass ein Fenster aufgeht (``GetOptions``/``GetFolder`` lesen
    zurueck, was gesetzt wurde). Der Aufrufer gibt den Dialog frei
    (:func:`freigeben`). Erwartet ein eingerichtetes COM im Faden.

    Raises:
        OrdnerwahlFehler: Ein Schritt scheiterte; nichts bleibt belegt.
    """
    dialog = ctypes.c_void_p()
    clsid, iid = _guid(CLSID_FILEOPENDIALOG), _guid(IID_IFILEOPENDIALOG)
    _pruefen(_api()["CoCreateInstance"](ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER,
                                        ctypes.byref(iid), ctypes.byref(dialog)),
             "CoCreateInstance(FileOpenDialog)")
    try:
        optionen = ctypes.c_uint32()
        _pruefen(_methode(dialog, _GET_OPTIONS, ctypes.POINTER(ctypes.c_uint32))(
            dialog, ctypes.byref(optionen)), "IFileDialog.GetOptions")
        _pruefen(_methode(dialog, _SET_OPTIONS, ctypes.c_uint32)(
            dialog, optionen.value | OPTIONEN), "IFileDialog.SetOptions")
        if titel:
            _pruefen(_methode(dialog, _SET_TITLE, ctypes.c_wchar_p)(dialog, titel),
                     "IFileDialog.SetTitle")
        if startordner and os.path.isdir(startordner):
            try:
                ordner = eintrag_zu_pfad(os.path.abspath(startordner))
            except OrdnerwahlFehler as exc:
                # Ein Startordner ist Komfort - ohne ihn oeffnet der Dialog,
                # wo er zuletzt war.
                logger.debug("Startordner nicht gesetzt: %s", exc)
            else:
                try:
                    _pruefen(_methode(dialog, _SET_FOLDER, ctypes.c_void_p)(dialog, ordner),
                             "IFileDialog.SetFolder")
                finally:
                    _freigeben(ordner)
    except BaseException:
        _freigeben(dialog)
        raise
    return dialog


def optionen_lesen(dialog: ctypes.c_void_p) -> int:
    """``GetOptions`` - was der Dialog an Optionen traegt."""
    optionen = ctypes.c_uint32()
    _pruefen(_methode(dialog, _GET_OPTIONS, ctypes.POINTER(ctypes.c_uint32))(
        dialog, ctypes.byref(optionen)), "IFileDialog.GetOptions")
    return optionen.value


def startordner_lesen(dialog: ctypes.c_void_p) -> str:
    """``GetFolder`` - vor dem Zeigen der Ordner, in dem der Dialog aufgehen wird."""
    ordner = ctypes.c_void_p()
    hr = _methode(dialog, _GET_FOLDER, ctypes.POINTER(ctypes.c_void_p))(dialog, ctypes.byref(ordner))
    if hr < 0 or not ordner.value:
        return ""
    try:
        return _anzeigename(ordner)
    finally:
        _freigeben(ordner)


def freigeben(objekt: ctypes.c_void_p) -> None:
    """Gibt einen Dialog (oder ein anderes COM-Objekt dieses Moduls) frei."""
    _freigeben(objekt)


def _com_einrichten() -> "bool | None":
    """COM im Faden einrichten. True: einrichten geglueckt (spaeter ``CoUninitialize``),
    False: war schon als STA eingerichtet - auch dann ist ``CoUninitialize`` faellig;
    None: der Faden ist ein MTA, der Dialog geht hier nicht."""
    hr = _api()["CoInitializeEx"](None, COINIT_APARTMENTTHREADED)
    if (hr & 0xFFFFFFFF) == RPC_E_CHANGED_MODE:
        return None
    if hr < 0:
        raise OrdnerwahlFehler("CoInitializeEx", hr)
    return hr == 0


def ordner_waehlen(*, titel: str = "", startordner: str = "",
                   besitzer: int = 0) -> "list[str] | None":
    """Zeigt den Ordnerdialog von Windows mit Mehrfachauswahl.

    Args:
        titel: Titelzeile des Dialogs.
        startordner: Hier geht er auf (wenn es den Ordner gibt).
        besitzer: Fenster (HWND), vor dem der Dialog modal steht; 0 fuer keins.

    Returns:
        Die gewaehlten Ordner in der Reihenfolge des Dialogs; eine leere Liste,
        wenn abgebrochen wurde. ``None``, wenn der Dialog hier nicht geht
        (nicht Windows, kein STA, Dialog nicht anzulegen) - dann nimmt der
        Aufrufer den Ordnerdialog von Tk.
    """
    if not verfuegbar():
        return None
    try:
        com = _com_einrichten()
    except OrdnerwahlFehler as exc:
        logger.warning("Ordnerdialog mit Mehrfachauswahl nicht verfuegbar: %s", exc)
        return None
    if com is None:
        logger.warning("Ordnerdialog mit Mehrfachauswahl: Faden ist kein STA")
        return None
    dialog = liste = None
    try:
        try:
            dialog = dialog_anlegen(titel, startordner)
        except OrdnerwahlFehler as exc:
            logger.warning("Ordnerdialog mit Mehrfachauswahl nicht anzulegen: %s", exc)
            return None
        hr = _methode(dialog, _SHOW, ctypes.c_void_p)(dialog, besitzer or None)
        if (hr & 0xFFFFFFFF) == HRESULT_ABGEBROCHEN:
            return []
        if hr < 0:
            logger.warning("Ordnerdialog liess sich nicht zeigen: HRESULT 0x%08X",
                           hr & 0xFFFFFFFF)
            return None
        liste = ctypes.c_void_p()
        _pruefen(_methode(dialog, _GET_RESULTS, ctypes.POINTER(ctypes.c_void_p))(
            dialog, ctypes.byref(liste)), "IFileOpenDialog.GetResults")
        return [os.path.normpath(p) for p in pfade_aus_liste(liste)]
    finally:
        if liste is not None:
            _freigeben(liste)
        if dialog is not None:
            _freigeben(dialog)
        _api()["CoUninitialize"]()
