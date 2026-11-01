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

    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

    # Ein Zustand je Wurzel: EINE Fensterprozedur, die alten Prozeduren und die aktuellen Ziele. Volllauf 01.11.2026
    # (als Administrator): Jeder Programmaufbau auf derselben Wurzel hing eine weitere Prozedur vor das Hauptfenster
    # - nach Dutzenden lief jede Nachricht durch Dutzende Python-Rueckrufe, bis update() mit einer Zugriffsverletzung
    # abstuerzte; und die Rueckrufe hielten jedes alte Programmfenster fest.
    zustand = getattr(root, "_ablegen_admin_zustand", None)
    if zustand is None:
        zustand = root._ablegen_admin_zustand = {"alte": {}, "ziele": [], "rueckruf": None}
    # Schwach gehalten: Ein neuer Aufbau ersetzt die Ziele, ohne das vorige Programmfenster am Leben zu halten.
    zustand["ziele"] = [(_schwach(w), _schwach(b)) for w, b in ziele]
    if zustand["rueckruf"] is None:
        zustand["rueckruf"] = _prozedur_bauen(root, zustand, ctypes, wintypes, user32, shell32, WNDPROC)
    rueckruf = zustand["rueckruf"]
    alte: dict[int, int] = zustand["alte"]
    eigene = ctypes.cast(rueckruf, ctypes.c_void_p).value

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
            if user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC) == eigene:
                eingerichtet += 1       # schon eingehaengt - ein zweites Mal riefe sich die Prozedur selbst auf
                continue
            for nachricht in (WM_DROPFILES, WM_COPYGLOBALDATA, WM_COPYDATA):
                user32.ChangeWindowMessageFilterEx(hwnd, nachricht, MSGFLT_ALLOW, None)
            vorher = user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, eigene)
            if not vorher:
                continue
            alte[hwnd] = vorher
            shell32.DragAcceptFiles(hwnd, True)
            eingerichtet += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ablage ueber WM_DROPFILES: Fenster %s nicht eingerichtet (%s)", hwnd, exc)
    logger.info("Ablage ueber WM_DROPFILES eingerichtet fuer %d von %d Fenstern %s", eingerichtet, len(fenster), fenster)
    return eingerichtet > 0


def _schwach(obj):
    """Schwacher Verweis auf ein Feld oder eine gebundene Methode; was keinen erlaubt, bleibt fest gehalten."""
    import weakref
    if hasattr(obj, "__self__") and hasattr(obj, "__func__"):
        return weakref.WeakMethod(obj)
    try:
        return weakref.ref(obj)
    except TypeError:
        return lambda: obj


def lebende_ziele(zustand: dict) -> list[tuple[object, Callable]]:
    """Die Ziele des Zustands, deren Feld und Behandler noch leben."""
    lebend = []
    for feld_ref, behandler_ref in zustand.get("ziele", ()):
        feld, behandler = feld_ref(), behandler_ref()
        if feld is not None and behandler is not None:
            lebend.append((feld, behandler))
    return lebend


def _prozedur_bauen(root, zustand: dict, ctypes, wintypes, user32, shell32, WNDPROC):
    """Die Fensterprozedur der Wurzel samt Abholtakt - einmal je Wurzel, sie liest die Ziele aus ``zustand``."""
    alte: dict[int, int] = zustand["alte"]

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
                behandler = ziel_waehlen((punkt.x, punkt.y), lebende_ziele(zustand))
                logger.info("Ablage ueber WM_DROPFILES: %d Pfad(e) bei (%d,%d)", len(namen), punkt.x, punkt.y)
                if behandler is not None and namen:
                    daten = pfade_in_liste(namen, root.tk)
                    warteschlange.put((behandler, daten))
                    logger.info("Ablage eingereiht")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ablage ueber WM_DROPFILES fehlgeschlagen: %s", exc)
            return 0
        return user32.CallWindowProcW(alte.get(hwnd_zahl), hwnd, msg, wparam, lparam)

    rueckruf = WNDPROC(_prozedur)      # bleibt ueber ``zustand`` an der Wurzel am Leben
    root.after(100, _abholen)
    return rueckruf
