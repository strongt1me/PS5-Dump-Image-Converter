# -*- coding: utf-8 -*-
"""Weboberflaechen der Konsole im Programmfenster zeigen (Windows, WebView2).

Wunsch des Nutzers vom 26.09.2026: "Wenn eine Weboberflaeche geoeffnet wird
(im Programm), soll diese bitte auch im Programm geoeffnet bzw. angezeigt
werden." Tk selbst zeigt kein modernes HTML samt JavaScript - die Oberflaeche
des Payload-Managers ist eine React-Anwendung. Unter Windows liegt eine
Browser-Engine aber bereit: die WebView2-Laufzeit (Edge). Ihr Controller legt
sein Fenster als Kind in ein beliebiges Fenster, hier in einen Tk-Rahmen.

Gebraucht werden

* ``pythonnet`` (MIT) - die Bruecke zu .NET Framework 4.x, das in Windows steckt;
* ``Microsoft.Web.WebView2.Core.dll`` und ``WebView2Loader.dll`` (Microsoft,
  BSD-artige Lizenz, von Microsoft signiert), geliefert mit ``pywebview``
  (BSD-3). Von pywebview selbst wird nichts benutzt, nur diese beiden Dateien;
* die WebView2-Laufzeit (in Windows 11 enthalten).

Fehlt davon etwas oder laeuft das Programm nicht unter Windows, nennt
:func:`verfuegbar` den Grund, und die Oberflaeche oeffnet wie bisher den
Browser. Das Modul bindet ``i18n`` nicht ein: Gruende sind Textschluessel.

**Faden:** Alles laeuft im Tk-Hauptfaden, der dafuer ein STA sein muss
(``CoInitializeEx``). WebView2 antwortet asynchron (.NET-Tasks), und die
Antworten kommen ueber die Nachrichtenschleife des Fadens - die von Tk. Wer
hier auf einen Task wartet, blockiert genau die Schleife, die ihn fertig
machen muesste. Deshalb fragt :meth:`Seite.schritt` die Tasks im Takt ab.

Gemessen am 26.09.2026 in einer getrennten Probeumgebung: Umgebung nach
0,07 s, Controller nach 0,35-0,46 s, Startseite des Payload-Managers nach
3,5 s geladen (langsame Leitung) und im Tk-Rahmen sichtbar (Bildschirmfoto);
die Seite des Webservers ("Homebrew Launcher") nach 2,3 s.
"""
from __future__ import annotations

import ctypes
import importlib.util
import os
import sys

#: Textschluessel fuer "warum nicht eingebettet".
GRUND_PLATTFORM = "webseite.grund_plattform"
GRUND_PYTHONNET = "webseite.grund_pythonnet"
GRUND_DLL = "webseite.grund_dll"
GRUND_LAUFZEIT = "webseite.grund_laufzeit"
GRUND_FADEN = "webseite.grund_faden"
GRUND_START = "webseite.grund_start"

#: Kennung der WebView2-Laufzeit in den Registrierungsschluesseln von EdgeUpdate.
_LAUFZEIT_KENNUNG = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
#: Unterordner im gebauten Programm (die .spec legt beide DLLs dort ab).
BUENDEL_ORDNER = "webview2"
CORE_DLL = "Microsoft.Web.WebView2.Core.dll"
LOADER_DLL = "WebView2Loader.dll"

_RPC_E_CHANGED_MODE = 0x80010106
#: Die geladenen .NET-Typen - einmal je Prozess (:func:`_net_laden`).
_net: "dict | None" = None


def dll_ordner() -> str:
    """Der Ordner mit ``Microsoft.Web.WebView2.Core.dll`` - oder "".

    Im gebauten Programm liegt er im Buendel (:data:`BUENDEL_ORDNER`), aus dem
    Quelltext im Paket ``webview`` (pywebview) unter ``lib``. Gefunden wird
    das Paket, ohne es zu importieren.
    """
    basis = getattr(sys, "_MEIPASS", None)
    if basis:
        ordner = os.path.join(basis, BUENDEL_ORDNER)
        return ordner if os.path.isfile(os.path.join(ordner, CORE_DLL)) else ""
    try:
        spec = importlib.util.find_spec("webview")
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.submodule_search_locations:
        return ""
    for paket in spec.submodule_search_locations:
        ordner = os.path.join(paket, "lib")
        if os.path.isfile(os.path.join(ordner, CORE_DLL)):
            return ordner
    return ""


def loader_pfad(ordner: str) -> str:
    """``WebView2Loader.dll`` fuer 64 Bit - flach im Buendel oder unter runtimes."""
    if not ordner:
        return ""
    for kandidat in (os.path.join(ordner, LOADER_DLL),
                     os.path.join(ordner, "runtimes", "win-x64", "native", LOADER_DLL)):
        if os.path.isfile(kandidat):
            return kandidat
    return ""


def laufzeit_version() -> str:
    """Die installierte WebView2-Laufzeit (Rechner oder Benutzer), "" = keine."""
    if sys.platform != "win32":
        return ""
    import winreg
    for wurzel, pfad in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients")):
        try:
            with winreg.OpenKey(wurzel, pfad + "\\" + _LAUFZEIT_KENNUNG) as schluessel:
                wert, _typ = winreg.QueryValueEx(schluessel, "pv")
        except OSError:
            continue
        if str(wert or "").strip() not in ("", "0.0.0.0"):
            return str(wert).strip()
    return ""


def verfuegbar() -> "tuple[bool, str]":
    """Laesst sich eine Seite einbetten? ``(True, "")`` oder ``(False, grund)``."""
    if sys.platform != "win32":
        return False, GRUND_PLATTFORM
    if importlib.util.find_spec("pythonnet") is None:
        return False, GRUND_PYTHONNET
    if not loader_pfad(dll_ordner()):
        return False, GRUND_DLL
    if not laufzeit_version():
        return False, GRUND_LAUFZEIT
    return True, ""


def _net_laden(ordner: str) -> dict:
    """Laedt .NET und die WebView2-Typen - einmal je Prozess, im Hauptfaden.

    Der Faden wird dabei STA. War er schon MTA, geht es nicht
    (``RPC_E_CHANGED_MODE``) - dann bleibt es beim Browser.
    """
    global _net
    if _net is not None:
        return _net
    ergebnis = ctypes.windll.ole32.CoInitializeEx(None, 2) & 0xFFFFFFFF
    if ergebnis == _RPC_E_CHANGED_MODE:
        raise OSError(GRUND_FADEN)
    # Vorgeladen findet .NET den Loader ueber den Namen, egal wo er liegt.
    ctypes.WinDLL(loader_pfad(ordner))
    from pythonnet import load
    load("netfx")
    import clr
    clr.AddReference("System.Drawing")
    clr.AddReference(os.path.join(ordner, CORE_DLL))
    from Microsoft.Web.WebView2.Core import CoreWebView2Environment
    from System import IntPtr
    from System.Drawing import Rectangle
    _net = {"Umgebung": CoreWebView2Environment, "IntPtr": IntPtr, "Rechteck": Rectangle}
    return _net


def _kurz(fehler) -> str:
    """Die erste Zeile einer (.NET-)Fehlermeldung - die ganze ist seitenlang."""
    text = str(fehler or "").strip()
    return text.splitlines()[0][:200] if text else ""


class Seite:
    """Eine eingebettete Webseite in einem Fenster (dem HWND eines Tk-Rahmens).

    :meth:`starten` legt die Umgebung an; :meth:`schritt` holt im Takt
    Umgebung und Controller ab und fuehrt dann aus, was vorher bestellt wurde
    (Adresse, Groesse, Sichtbarkeit). Zustaende: neu, startet, bereit,
    fehler, zu.
    """

    def __init__(self, hwnd: int, datenordner: str):
        self.hwnd = int(hwnd)
        self.datenordner = datenordner
        self.zustand = "neu"
        self.fehler = ""
        #: (erfolg, status) der letzten Navigation, None = laeuft noch.
        self.navigation: "tuple[bool, str] | None" = None
        self._ziel = ""
        self._groesse = (0, 0)
        self._sichtbar = True
        self._net: dict = {}
        self._umgebung_task = None
        self._controller_task = None
        self._controller = None

    def starten(self) -> None:
        if self.zustand != "neu":
            return
        try:
            self._net = _net_laden(dll_ordner())
            self._umgebung_task = self._net["Umgebung"].CreateAsync(
                None, self.datenordner, None)
            self.zustand = "startet"
        except Exception as fehler:     # .NET und COM melden eigene Typen
            self._scheitern(fehler)

    def _scheitern(self, fehler) -> None:
        self.zustand = "fehler"
        self.fehler = _kurz(fehler) or GRUND_START

    def schritt(self) -> None:
        """Im Takt aus dem Hauptfaden - wartet nie, fragt nur nach."""
        if self.zustand != "startet":
            return
        try:
            if self._controller_task is None:
                task = self._umgebung_task
                if not task.IsCompleted:
                    return
                if task.IsFaulted:
                    self._scheitern(task.Exception)
                    return
                self._controller_task = task.Result.CreateCoreWebView2ControllerAsync(
                    self._net["IntPtr"](self.hwnd))
                return
            task = self._controller_task
            if not task.IsCompleted:
                return
            if task.IsFaulted:
                self._scheitern(task.Exception)
                return
            self._controller = task.Result
            self._controller.CoreWebView2.NavigationCompleted += self._navigiert
            self.zustand = "bereit"
            self._anwenden()
        except Exception as fehler:
            self._scheitern(fehler)

    def _navigiert(self, _sender, args) -> None:
        self.navigation = (bool(args.IsSuccess), str(args.WebErrorStatus))

    def _anwenden(self) -> None:
        self._groesse_anwenden()
        self._controller.IsVisible = self._sichtbar
        if self._ziel:
            ziel, self._ziel = self._ziel, ""
            self._controller.CoreWebView2.Navigate(ziel)

    def _groesse_anwenden(self) -> None:
        breite, hoehe = self._groesse
        self._controller.Bounds = self._net["Rechteck"](0, 0, max(0, breite), max(0, hoehe))

    def navigieren(self, adresse: str) -> None:
        self._ziel = str(adresse or "")
        self.navigation = None
        if self.zustand == "bereit":
            self._anwenden()

    def neu_laden(self) -> None:
        if self.zustand == "bereit":
            self.navigation = None
            self._controller.CoreWebView2.Reload()

    def groesse_setzen(self, breite: int, hoehe: int) -> None:
        self._groesse = (int(breite), int(hoehe))
        if self.zustand == "bereit":
            self._groesse_anwenden()

    def sichtbar_setzen(self, sichtbar: bool) -> None:
        self._sichtbar = bool(sichtbar)
        if self.zustand == "bereit":
            self._controller.IsVisible = self._sichtbar

    @property
    def titel(self) -> str:
        if self.zustand != "bereit":
            return ""
        try:
            return str(self._controller.CoreWebView2.DocumentTitle or "")
        except Exception:
            return ""

    def schliessen(self) -> None:
        if self._controller is not None:
            try:
                self._controller.Close()
            except Exception:
                pass
        self._controller = None
        self.zustand = "zu"
