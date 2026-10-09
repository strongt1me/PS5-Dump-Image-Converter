# -*- coding: utf-8 -*-
"""Farbe der Fenster-Titelleiste - dunkel graublau (seit v1.9.71, Nutzerwunsch 09.10.2026).

Windows 11 laesst Programme die Farbe der Titelleiste selbst bestimmen: ``DwmSetWindowAttribute`` mit
``DWMWA_CAPTION_COLOR`` (35), ``DWMWA_TEXT_COLOR`` (36) und ``DWMWA_BORDER_COLOR`` (34) ab Build 22000. Mit
``DWMWA_USE_IMMERSIVE_DARK_MODE`` (20) werden die Fensterknoepfe (Minimieren, Maximieren, Schliessen) weiss.

* Gefaerbt wird jedes Fenster des Programms, auch spaeter geoeffnete (:func:`anwenden` am ``<Map>``-Ereignis, im
  Hauptprogramm ``_fenster_titelfarben_einrichten``). Das Design **Hell** behaelt die helle Systemleiste
  (:func:`zuruecksetzen`).
* Auf Windows 10, Linux und macOS gibt es diese Schnittstelle nicht - dort bleibt die Leiste, wie sie ist; die
  Funktionen melden ``False`` und tun nichts.
* Nicht erreichbar sind die Standarddialoge von Windows (Datei- und Ordnerwahl): Sie gehoeren dem System.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import weakref
from typing import Callable

logger = logging.getLogger("PS5Converter.fenster_titelfarbe")

#: Das gewaehlte Graublau (Nutzer 09.10.2026: "B") und die helle Schrift darauf.
DUNKEL_BLAUGRAU = "#2A3441"
SCHRIFT_HELL = "#E8EDF4"

#: Kennungen von ``DwmSetWindowAttribute``.
_DUNKLER_MODUS = 20
_RAND_FARBE = 34
_KAPPE_FARBE = 35
_TEXT_FARBE = 36
#: ``DWMWA_COLOR_DEFAULT``: die Farbe des Systems.
_STANDARD = 0xFFFFFFFF
#: Erst ab diesem Build gibt es Titelleisten-Farben (Windows 11 21H2).
_MINDEST_BUILD = 22000


def _windows_build() -> int:
    """Die Buildnummer von Windows, ``0`` ausserhalb von Windows."""
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except (AttributeError, OSError):
        return 0


def unterstuetzt() -> bool:
    """Kennt dieses System Titelleisten-Farben (Windows 11)?"""
    return _windows_build() >= _MINDEST_BUILD


def farbwert(farbe: str) -> int:
    """``#RRGGBB`` als ``COLORREF`` (``0x00BBGGRR``)."""
    text = farbe.lstrip("#")
    if len(text) != 6:
        raise ValueError("Farbe erwartet #RRGGBB: %r" % farbe)
    r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    return r | (g << 8) | (b << 16)


def _dwm():
    """Die Bibliothek ``dwmapi`` (in den Tests ersetzt)."""
    dwm = ctypes.windll.dwmapi
    return dwm


def _setzen(hwnd: int, kennung: int, wert: int) -> bool:
    ablage = ctypes.c_uint(wert)
    ergebnis = _dwm().DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_uint(kennung), ctypes.byref(ablage),
                                            ctypes.c_uint(4))
    return ergebnis == 0


def fenster_kennung(widget) -> int:
    """Das Windows-Fensterhandle eines Tk-Fensters (der aeussere Rahmen mit der Titelleiste)."""
    innen = int(widget.winfo_id())
    aussen = ctypes.windll.user32.GetParent(ctypes.c_void_p(innen))
    return int(aussen or innen)


def faerben(widget, kappe: str = DUNKEL_BLAUGRAU, text: str = SCHRIFT_HELL) -> bool:
    """Faerbt die Titelleiste (und den Rand) des Fensters. ``True``, wenn Windows es angenommen hat."""
    if not unterstuetzt():
        return False
    hwnd = fenster_kennung(widget)
    farbe = farbwert(kappe)
    ok = _setzen(hwnd, _DUNKLER_MODUS, 1)
    ok = _setzen(hwnd, _KAPPE_FARBE, farbe) and ok
    ok = _setzen(hwnd, _TEXT_FARBE, farbwert(text)) and ok
    ok = _setzen(hwnd, _RAND_FARBE, farbe) and ok
    return ok


def zuruecksetzen(widget) -> bool:
    """Gibt die Titelleiste an die Farben des Systems zurueck (Design Hell)."""
    if not unterstuetzt():
        return False
    hwnd = fenster_kennung(widget)
    ok = _setzen(hwnd, _DUNKLER_MODUS, 0)
    for kennung in (_KAPPE_FARBE, _TEXT_FARBE, _RAND_FARBE):
        ok = _setzen(hwnd, kennung, _STANDARD) and ok
    return ok


def anwenden(widget, dunkel: bool) -> bool:
    """Faerbt oder setzt zurueck, je nachdem, ob das Design dunkel ist. Fenster ohne Titelleiste bleiben unberuehrt."""
    try:
        if widget.winfo_class() not in ("Toplevel", "Tk"):
            return False
        if widget.wm_overrideredirect():
            return False          # Tooltips, Einblendungen: kein Fensterrahmen
        return faerben(widget) if dunkel else zuruecksetzen(widget)
    except Exception as exc:  # noqa: BLE001 - eine Titelleiste ist nie einen Absturz wert
        logger.debug("Titelleiste nicht gefaerbt: %s", exc)
        return False


def _fenster_unter(wurzel) -> list:
    """Die Wurzel und alle Toplevel-Fenster darunter."""
    gefunden = [wurzel]
    wartend = list(wurzel.winfo_children())
    while wartend:
        w = wartend.pop()
        try:
            if w.winfo_class() == "Toplevel":
                gefunden.append(w)
            wartend.extend(w.winfo_children())
        except Exception:  # noqa: BLE001 - ein Fenster, das gerade verschwindet
            continue
    return gefunden


def aktualisieren(wurzel) -> int:
    """Faerbt alle offenen Fenster neu (nach einem Designwechsel). Gibt die Zahl der angenommenen Fenster zurueck."""
    dunkel = bool(getattr(wurzel, "_fenster_titelfarbe_dunkel", lambda: True)())
    return sum(1 for w in _fenster_unter(wurzel) if anwenden(w, dunkel))


def _antwortfunktion(ist_dunkel: Callable[[], bool]) -> Callable[[], bool]:
    """Verpackt ``ist_dunkel`` so, dass die Wurzel das Programmfenster nicht festhaelt.

    Die Wurzel ueberlebt jedes Programmfenster (in den Tests baut jede Klasse ihres ab, die Wurzel bleibt). Eine
    gebundene Methode des Fensters an ihr haette es am Leben gehalten. Ist das Fenster weg, gilt dunkel.
    """
    if getattr(ist_dunkel, "__self__", None) is None or not hasattr(ist_dunkel, "__func__"):
        return ist_dunkel         # eine gewoehnliche Funktion haelt kein Fenster fest
    methode = weakref.WeakMethod(ist_dunkel)

    def antwort() -> bool:
        funktion = methode()
        return True if funktion is None else bool(funktion())

    return antwort


def ist_eingerichtet(wurzel) -> bool:
    """Haengen die ``<Map>``-Haken dieses Moduls noch an der Wurzel?

    Gemessen wird am Stand von Tk, nicht an einer Merkmarke der Wurzel: Wer die Bindungen zuruecksetzt (die Tests
    nach der Klasse eines Programmfensters), nimmt die Haken mit - eine Marke liesse das Neubinden dann ausfallen.
    """
    namen = getattr(wurzel, "_fenster_titelfarbe_bindung", ())
    if not namen:
        return False
    try:
        skripte = "%s\n%s" % (wurzel.bind_class("Toplevel", "<Map>"), wurzel.bind("<Map>"))
    except Exception as exc:  # noqa: BLE001 - die Wurzel wird gerade abgebaut
        logger.debug("Bindungen der Wurzel nicht lesbar: %s", exc)
        return False
    # Tkinter schreibt jeden Haken als ``if {"[<Befehl> %# ...]" == "break"} break`` - so kann kein anderer Befehl
    # mit zufaellig gleichem Namensende gemeint sein.
    return all(("[%s " % name) in skripte for name in namen)


def einrichten(wurzel, ist_dunkel: Callable[[], bool]) -> None:
    """Haengt die Faerbung an jedes Fenster des Programms - auch an spaeter geoeffnete.

    ``ist_dunkel`` sagt zu jedem Zeitpunkt, ob das aktive Design eine dunkle Leiste bekommt (Hell: nein). Die
    Haken werden je Wurzel nur einmal angelegt (:func:`ist_eingerichtet`); ein neues Programmfenster auf derselben
    Wurzel (Tests) tauscht nur die Antwortfunktion aus.
    """
    wurzel._fenster_titelfarbe_dunkel = _antwortfunktion(ist_dunkel)
    if not ist_eingerichtet(wurzel):

        def bei_map(ereignis) -> None:
            w = ereignis.widget
            if not hasattr(w, "winfo_class"):
                return            # ein Fenster, das Tk selbst angelegt hat (Auswahlliste einer Klappliste)
            if w is wurzel or w.winfo_class() == "Toplevel":
                anwenden(w, bool(wurzel._fenster_titelfarbe_dunkel()))

        wurzel._fenster_titelfarbe_bindung = (wurzel.bind_class("Toplevel", "<Map>", bei_map, add="+"),
                                              wurzel.bind("<Map>", bei_map, add="+"))
    aktualisieren(wurzel)
