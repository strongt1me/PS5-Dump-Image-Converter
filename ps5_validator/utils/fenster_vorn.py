# -*- coding: utf-8 -*-
"""Haelt Fenster vor ihrem Eltern-Fenster - auch rahmenlose.

Hintergrund (21.10.2026, gemessen an der Z-Reihenfolge unter Windows): Ein ``Toplevel`` mit
``overrideredirect(True)`` bleibt auch nach ``transient(eltern)`` **nicht** vor dem Hauptfenster - ein Klick
daneben holt das Hauptfenster nach vorn, und das rahmenlose Fenster verschwindet dahinter (Spiel-Info - Updates &
Patches; der Knopf wirkte dann wie "zweimal klicken": der erste Klick schloss das verdeckte Fenster, der zweite
oeffnete es neu). Ein normales Fenster mit ``transient`` bleibt dagegen oben. Hier wird deshalb unter Windows der
Win32-Besitzer (``GWLP_HWNDPARENT``) des rahmenlosen Fensters gesetzt: Ein Fenster mit Besitzer liegt immer vor ihm,
auch nach Minimieren und Wiederherstellen des Besitzers (gemessen). Ohne Windows haelt ein ``<FocusIn>`` des
Eltern-Fensters das Fenster vorn.
"""
from __future__ import annotations

import logging
import sys
import tkinter as tk

logger = logging.getLogger(__name__)

_GA_ROOT = 2
_GWLP_HWNDPARENT = -8


def _oberstes_handle(widget) -> int:
    """Das Win32-Handle des Fensters, zu dem ``widget`` gehoert (0, wenn es keines gibt)."""
    import ctypes
    from ctypes import wintypes

    benutzer = ctypes.windll.user32
    benutzer.GetAncestor.restype = wintypes.HWND
    benutzer.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    return int(benutzer.GetAncestor(widget.winfo_id(), _GA_ROOT) or 0)


def besitzer_setzen(fenster, eltern) -> bool:
    """Macht ``eltern`` unter Windows zum Besitzer von ``fenster`` - das Fenster liegt dann stets davor.

    Returns:
        ``True``, wenn der Besitzer nach dem Setzen gelesen werden kann; ``False`` ohne Windows oder bei einem Fehler.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        fenster.update_idletasks()
        kind = _oberstes_handle(fenster)
        besitzer = _oberstes_handle(eltern)
        if not kind or not besitzer or kind == besitzer:
            return False
        benutzer = ctypes.windll.user32
        setzen = getattr(benutzer, "SetWindowLongPtrW", None) or benutzer.SetWindowLongW
        lesen = getattr(benutzer, "GetWindowLongPtrW", None) or benutzer.GetWindowLongW
        setzen.restype = ctypes.c_void_p
        setzen.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        lesen.restype = ctypes.c_void_p
        lesen.argtypes = [wintypes.HWND, ctypes.c_int]
        setzen(kind, _GWLP_HWNDPARENT, besitzer)
        return int(lesen(kind, _GWLP_HWNDPARENT) or 0) == besitzer
    except Exception as exc:  # noqa: BLE001 - ohne Besitzer geht es auch, nur ohne den Halt
        logger.debug("Besitzer fuer rahmenloses Fenster nicht setzbar: %s", exc)
        return False


def rahmenlos_vorn_halten(fenster, eltern) -> bool:
    """Haelt ein rahmenloses Fenster vor ``eltern``; gibt zurueck, ob ein fester Besitzer gesetzt wurde."""
    if besitzer_setzen(fenster, eltern):
        return True
    # Rueckfall (X11/macOS): kommt das Eltern-Fenster nach vorn, holt es das Fenster nach.
    try:
        oben = eltern.winfo_toplevel()

        def _nachziehen(_e=None) -> None:
            try:
                if fenster.winfo_exists() and fenster.winfo_viewable():
                    fenster.after_idle(fenster.lift)
            except tk.TclError:
                pass

        oben.bind("<FocusIn>", _nachziehen, add="+")
    except tk.TclError as exc:
        logger.debug("Rueckfall fuer rahmenloses Fenster nicht bindbar: %s", exc)
    return False


def aktives_fenster(wurzel):
    """Das Programmfenster, das gerade den Fokus hat - sonst ``wurzel``.

    Meldungen und Dateidialoge gehoeren an dieses Fenster, nicht immer ans Hauptfenster: Ein Dialog, der dem
    Hauptfenster gehoert, faellt hinter das Werkzeugfenster, das ihn ausgeloest hat, sobald man dieses anklickt.
    Nur im Hauptfaden aufrufen.
    """
    try:
        fokus = wurzel.focus_displayof()
        if fokus is not None:
            oben = fokus.winfo_toplevel()
            if oben.winfo_exists() and oben.winfo_viewable():
                return oben
    except (tk.TclError, KeyError, AttributeError):
        pass
    return wurzel
