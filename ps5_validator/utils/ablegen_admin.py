# -*- coding: utf-8 -*-
"""Ziehen und Ablegen fuer ein Programm, das als Administrator laeuft (Windows).

Das Programm startet sich selbst mit erhoehten Rechten neu. Der Explorer laeuft mit normalen Rechten, und
Windows (UIPI) laesst eine OLE-Ablage von dort in ein erhoehtes Fenster nicht durch - ``tkinterdnd2`` nutzt
genau diesen Weg, das Ablegen bleibt ohne jede Meldung wirkungslos.

Der aeltere Weg ueber ``WM_DROPFILES`` funktioniert dagegen, wenn das Fenster ihn ausdruecklich zulaesst
(``ChangeWindowMessageFilterEx`` fuer ``WM_DROPFILES``, ``WM_COPYGLOBALDATA`` und ``WM_COPYDATA``) und keine
OLE-Ablage fuer dasselbe Fenster angemeldet ist. Dieses Modul haengt sich dafuer in die Fensterprozeduren der
Zielfelder und des Hauptfensters ein.

**Nicht ueberall gemessen:** ob der Explorer die Ablage bei einem Tk-Kindfenster bis zum Hauptfenster
weiterreicht, zeigt nur der Versuch am laufenden Programm.
"""
from __future__ import annotations

import logging
import queue
import sys
from typing import Callable, Sequence

logger = logging.getLogger("PS5Converter.ablegen")

WM_DROPFILES = 0x0233
WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
MSGFLT_ALLOW = 1
GWL_WNDPROC = -4
GA_ROOT = 2


def pfade_in_liste(pfade: Sequence[str], tk) -> tuple[str, ...]:
    """Die Pfade als Tupel: ``splitlist`` der Behandler reicht ein Tupel unveraendert durch (Leerzeichen bleiben heil)."""
    return tuple(pfade)


class _Ereignis:
    """Das Wenige, das die Ablage-Behandler von ``tkinterdnd2`` brauchen: ``.data``."""

    def __init__(self, data: str) -> None:
        self.data = data


def ziel_waehlen(punkt: tuple[int, int], ziele: Sequence[tuple[object, Callable]]):
    """Der Behandler des Feldes, in dem der Bildschirmpunkt liegt - sonst der des ersten Feldes."""
    if not ziele:
        return None
    x, y = punkt
    for widget, behandler in ziele:
        try:
            links, oben = widget.winfo_rootx(), widget.winfo_rooty()
            if links <= x < links + widget.winfo_width() and oben <= y < oben + widget.winfo_height():
                return behandler
        except Exception:  # noqa: BLE001
            continue
    return ziele[0][1]


def installieren(root, ziele: Sequence[tuple[object, Callable]]) -> bool:
    """Meldet ``WM_DROPFILES`` fuer das Hauptfenster und die Zielfelder an. ``True``, wenn es eingerichtet ist.

    Args:
        root: die Tk-Wurzel.
        ziele: ``(Feld, Behandler)`` - der Behandler bekommt ein Objekt mit ``.data`` (Tcl-Liste der Pfade).
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # noqa: BLE001
        return False

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = LRESULT
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryPoint.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.POINT)]
    shell32.DragFinish.argtypes = [wintypes.HANDLE]
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]

    stuecke = getattr(root, "_ablegen_admin_stuecke", None)
    if stuecke is None:
        stuecke = root._ablegen_admin_stuecke = []   # haelt Rueckruf und alte Prozedur am Leben
    alte: dict[int, int] = {}

    def _pfade(hdrop) -> list[str]:
        anzahl = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        namen = []
        for i in range(anzahl):
            laenge = shell32.DragQueryFileW(hdrop, i, None, 0)
            puffer = ctypes.create_unicode_buffer(laenge + 1)
            shell32.DragQueryFileW(hdrop, i, puffer, laenge + 1)
            namen.append(puffer.value)
        return namen

    warteschlange: queue.SimpleQueue = queue.SimpleQueue()

    def _abholen():
        # Tk-Aufrufe gehoeren nicht in die Fensterprozedur: sie reiht nur ein, dieser Takt fuehrt aus.
        try:
            while True:
                try:
                    behandler, daten = warteschlange.get_nowait()
                except queue.Empty:
                    break
                _aufrufen(behandler, daten)
            root.after(100, _abholen)
        except Exception:  # noqa: BLE001  - Fenster schon zerstoert
            pass

    def _aufrufen(behandler, daten):
        logger.info("Ablage wird uebergeben: %s", daten)
        try:
            behandler(_Ereignis(daten))
        except Exception:  # noqa: BLE001
            logger.exception("Ablage-Behandler fehlgeschlagen")

    def _prozedur(hwnd, msg, wparam, lparam):
        hwnd_zahl = int(hwnd or 0)
        if msg == WM_DROPFILES:
            logger.info("WM_DROPFILES angekommen bei Fenster %s", hwnd_zahl)
            try:
                punkt = wintypes.POINT()
                shell32.DragQueryPoint(wparam, ctypes.byref(punkt))
                namen = _pfade(wparam)
                shell32.DragFinish(wparam)
                user32.ClientToScreen(hwnd, ctypes.byref(punkt))
                behandler = ziel_waehlen((punkt.x, punkt.y), ziele)
                logger.info("Ablage ueber WM_DROPFILES: %d Pfad(e) bei (%d,%d)", len(namen), punkt.x, punkt.y)
                if behandler is not None and namen:
                    daten = pfade_in_liste(namen, root.tk)
                    warteschlange.put((behandler, daten))
                    logger.info("Ablage eingereiht")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ablage ueber WM_DROPFILES fehlgeschlagen: %s", exc)
            return 0
        return user32.CallWindowProcW(alte.get(hwnd_zahl), hwnd, msg, wparam, lparam)

    rueckruf = WNDPROC(_prozedur)
    stuecke.append(rueckruf)

    fenster: list[int] = []
    try:
        root.update_idletasks()
        innen = root.winfo_id()
        wurzel_hwnd = user32.GetAncestor(innen, GA_ROOT) or innen
        for kandidat in [wurzel_hwnd, innen] + [w.winfo_id() for w, _b in ziele]:
            if kandidat and int(kandidat) not in fenster:
                fenster.append(int(kandidat))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ablage ueber WM_DROPFILES: Fenster nicht ermittelt (%s)", exc)
        return False

    eingerichtet = 0
    for hwnd in fenster:
        try:
            for nachricht in (WM_DROPFILES, WM_COPYGLOBALDATA, WM_COPYDATA):
                user32.ChangeWindowMessageFilterEx(hwnd, nachricht, MSGFLT_ALLOW, None)
            vorher = user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, ctypes.cast(rueckruf, ctypes.c_void_p))
            if not vorher:
                continue
            alte[hwnd] = vorher
            shell32.DragAcceptFiles(hwnd, True)
            eingerichtet += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ablage ueber WM_DROPFILES: Fenster %s nicht eingerichtet (%s)", hwnd, exc)
    if eingerichtet:
        root.after(100, _abholen)
    logger.info("Ablage ueber WM_DROPFILES eingerichtet fuer %d von %d Fenstern %s", eingerichtet, len(fenster), fenster)
    return eingerichtet > 0
