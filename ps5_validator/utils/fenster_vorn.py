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


_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def _dwm_ecken_runden(hwnd: int) -> bool:
    """Bittet Windows 11, die Ecken des Fensters selbst rund zu zeichnen (gleich wie bei den Rahmenfenstern).

    Ohne Rahmen rundet Windows nichts von allein; mit diesem Attribut schon (gemessen am 11.11.2026 an einem
    ``overrideredirect``-Fenster unter Windows 11, Build 26200: die Ecke zeigt danach den Untergrund, glatt gezeichnet).
    Windows 10 kennt das Attribut nicht und meldet einen Fehler - dann bleibt nur die Fensterregion.
    """
    try:
        import ctypes
        from ctypes import wintypes

        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        wert = ctypes.c_int(_DWMWCP_ROUND)
        return dwm.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(wert), ctypes.sizeof(wert)) == 0
    except (OSError, AttributeError, ValueError) as exc:
        logger.debug("DWM-Ecken nicht setzbar: %s", exc)
        return False


def _region_runden(fenster, hwnd: int, radius: int) -> bool:
    """Schneidet die Ecken ueber die Fensterregion rund (Rueckfall fuer Windows 10; die Kante ist nicht geglaettet)."""
    try:
        import ctypes
        from ctypes import wintypes

        benutzer = ctypes.windll.user32
        gdi = ctypes.windll.gdi32
        benutzer.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
        benutzer.SetWindowRgn.restype = ctypes.c_int
        benutzer.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        gdi.CreateRoundRectRgn.restype = ctypes.c_void_p
        gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi.DeleteObject.argtypes = [ctypes.c_void_p]
        rechteck = wintypes.RECT()
        if not benutzer.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rechteck)):
            return False
        breite = rechteck.right - rechteck.left
        hoehe = rechteck.bottom - rechteck.top
        if breite <= 2 * radius or hoehe <= 2 * radius:
            return False
        # +1: CreateRoundRectRgn laesst die rechte und untere Kante weg.
        region = gdi.CreateRoundRectRgn(0, 0, breite + 1, hoehe + 1, radius * 2, radius * 2)
        if not region:
            return False
        if not benutzer.SetWindowRgn(ctypes.c_void_p(hwnd), ctypes.c_void_p(region), True):
            gdi.DeleteObject(ctypes.c_void_p(region))     # nur freigeben, wenn Windows sie nicht uebernommen hat
            return False
        return True
    except (OSError, AttributeError, ValueError) as exc:
        logger.debug("Fensterregion nicht setzbar: %s", exc)
        return False


def ecken_runden(fenster, radius: int = 14, *, vorbereiten: bool = True, verfahren: str = "") -> str:
    """Rundet die Ecken eines rahmenlosen Fensters (nur Windows; sonst bleibt es eckig und es wird ``""`` gemeldet).

    Windows 11: ueber das DWM-Attribut (glatt, wie die Rahmenfenster; der Radius ist dann der des Systems).
    Sonst: ueber die Fensterregion mit ``radius`` Pixeln, nachgefuehrt bei jeder Groessenaenderung.

    Args:
        vorbereiten: ``update_idletasks`` vorher rufen, damit das Win32-Fenster sicher existiert (nicht aus einem
            Ereignis heraus, das selbst gerade das Fenster zeigt).
        verfahren: ``"region"`` erzwingt die Region (Messung/Test); sonst waehlt die Funktion selbst.

    Returns:
        ``"dwm"``, ``"region"`` oder ``""``.
    """
    if sys.platform != "win32" or radius <= 0:
        return ""
    try:
        if vorbereiten:
            fenster.update_idletasks()
        hwnd = _oberstes_handle(fenster)
        if not hwnd:
            return ""
        if verfahren != "region" and _dwm_ecken_runden(hwnd):
            return "dwm"
        if not _region_runden(fenster, hwnd, radius):
            return ""

        stand = {"geplant": None}

        def _nachfuehren(_e=None) -> None:
            stand["geplant"] = None
            try:
                if fenster.winfo_exists():
                    _region_runden(fenster, _oberstes_handle(fenster), radius)
            except tk.TclError:
                pass

        def _bei_groesse(e) -> None:
            if e.widget is not fenster:
                return
            try:
                if stand["geplant"] is not None:
                    fenster.after_cancel(stand["geplant"])
                stand["geplant"] = fenster.after(40, _nachfuehren)
            except tk.TclError:
                pass

        fenster.bind("<Configure>", _bei_groesse, add="+")
        return "region"
    except (tk.TclError, OSError, AttributeError) as exc:
        logger.debug("Ecken nicht rundbar: %s", exc)
        return ""


class GroessenGriff:
    """Macht ein rahmenloses Fenster an Seiten und unteren Ecken groesser und kleiner ziehbar.

    Ein ``overrideredirect``-Fenster hat keinen Rand, den das System greifen koennte (``resizable(True, True)``
    allein aendert daran nichts). Der Griff liest die Maus am Fenster ab (Bindung am Toplevel, sie erreicht auch alle
    Kinder), zeigt am Rand den passenden Zeiger und setzt beim Ziehen die Geometrie. Oben bleibt die Titelleiste zum
    Verschieben. Die Titelleiste fragt ``zone`` vor ihrem eigenen Ziehen, damit Rand und Verschieben sich nicht
    in die Quere kommen.
    """

    _ZEIGER_WIN = {"e": "size_we", "w": "size_we", "s": "size_ns", "se": "size_nw_se", "sw": "size_ne_sw"}
    _ZEIGER_X11 = {"e": "sb_h_double_arrow", "w": "sb_h_double_arrow", "s": "sb_v_double_arrow",
                   "se": "bottom_right_corner", "sw": "bottom_left_corner"}
    _ZEIGER_MAC = {"e": "resizeleftright", "w": "resizeleftright", "s": "resizeupdown",
                   "se": "crosshair", "sw": "crosshair"}

    def __init__(self, fenster, min_breite: int, min_hoehe: int, rand: int = 6, ecke: int = 18) -> None:
        self.fenster = fenster
        self.min_breite = max(1, int(min_breite))
        self.min_hoehe = max(1, int(min_hoehe))
        self.rand = max(2, int(rand))
        self.ecke = max(self.rand * 2, int(ecke))
        self._zeiger = ""
        self._zug: dict | None = None
        fenster.bind("<Motion>", self._bewegt, add="+")
        fenster.bind("<ButtonPress-1>", self._gedrueckt, add="+")
        fenster.bind("<B1-Motion>", self._gezogen, add="+")
        fenster.bind("<ButtonRelease-1>", self._losgelassen, add="+")

    def zone(self, x_root: int, y_root: int) -> str:
        """``""`` mitten im Fenster, sonst ``"e"``, ``"w"``, ``"s"``, ``"se"`` oder ``"sw"``."""
        try:
            wx = x_root - self.fenster.winfo_rootx()
            wy = y_root - self.fenster.winfo_rooty()
            breite = self.fenster.winfo_width()
            hoehe = self.fenster.winfo_height()
        except tk.TclError:
            return ""
        links = wx < self.rand
        rechts = wx >= breite - self.rand
        unten = wy >= hoehe - self.rand
        if unten:
            links = links or wx < self.ecke
            rechts = rechts or wx >= breite - self.ecke
        elif (links or rechts) and wy >= hoehe - self.ecke:
            unten = True
        if not (links or rechts or unten):
            return ""
        if links and rechts:                        # sehr schmales Fenster: die naehere Seite gilt
            rechts = (breite - wx) < wx
            links = not rechts
        if unten:
            return "s" + ("e" if rechts else "") + ("w" if links else "")
        return "e" if rechts else "w"

    def _zeiger_fuer(self, zone: str) -> str:
        if not zone:
            return ""
        if sys.platform == "win32":
            tabelle = self._ZEIGER_WIN
        elif sys.platform == "darwin":
            tabelle = self._ZEIGER_MAC
        else:
            tabelle = self._ZEIGER_X11
        return tabelle.get(zone, "")

    def _zeiger_setzen(self, zeiger: str) -> None:
        if zeiger == self._zeiger:
            return
        try:
            self.fenster.configure(cursor=zeiger)
            self._zeiger = zeiger
        except tk.TclError:
            pass

    def _bewegt(self, e) -> None:
        if self._zug is None:
            self._zeiger_setzen(self._zeiger_fuer(self.zone(e.x_root, e.y_root)))

    def _gedrueckt(self, e) -> None:
        zone = self.zone(e.x_root, e.y_root)
        if not zone:
            self._zug = None
            return
        f = self.fenster
        self._zug = {"zone": zone, "x": e.x_root, "y": e.y_root, "b": f.winfo_width(), "h": f.winfo_height(),
                     "fx": f.winfo_x(), "fy": f.winfo_y()}

    def _gezogen(self, e) -> None:
        zug = self._zug
        if zug is None:
            return
        dx = e.x_root - zug["x"]
        dy = e.y_root - zug["y"]
        breite, hoehe, x = zug["b"], zug["h"], zug["fx"]
        zone = zug["zone"]
        if "e" in zone:
            breite = max(self.min_breite, zug["b"] + dx)
        if "w" in zone:
            breite = max(self.min_breite, zug["b"] - dx)
            x = zug["fx"] + (zug["b"] - breite)
        if "s" in zone:
            hoehe = max(self.min_hoehe, zug["h"] + dy)
        try:
            self.fenster.geometry("%dx%d+%d+%d" % (breite, hoehe, x, zug["fy"]))
        except tk.TclError:
            self._zug = None

    def _losgelassen(self, _e=None) -> None:
        self._zug = None


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
