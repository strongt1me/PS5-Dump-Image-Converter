# -*- coding: utf-8 -*-
"""Bindungen am Toplevel, die ein Widget wieder abnimmt, wenn es zerstoert wird.

Eine Bindung, die ein kurzlebiges Widget an das (langlebige) Toplevel haengt, haelt dieses Widget samt Kindern und
Bildern fest: Das Tcl-Kommando der Bindung verweist auf eine Funktion, die das Widget kennt. Seit die beiden
PKG-Bereiche in einem Rahmen der Hauptfenster liegen (30.10.2026), ist das Toplevel das Hauptfenster - jede gebaute
Seite liess so ihre Rollflaeche, alle Kinder und alle Tk-Bilder zurueck (gemessen: +100 MB je Aufbau, ein Absturz des
Testlaufs bei 65 %). Die Rollflaeche haengt ihr Mausrad deshalb ueber ``an_toplevel_binden`` an.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable


def bindung_loesen(widget: tk.Misc, sequenz: str, kennung: str) -> None:
    """Nimmt genau eine Bindung (``kennung`` aus ``bind``) wieder ab - die anderen an derselben Sequenz bleiben.

    ``unbind(sequenz, kennung)`` tut das erst seit Python 3.13; aeltere Fassungen nahmen alle Bindungen der Sequenz mit.
    """
    try:
        zeilen = str(widget.tk.call("bind", widget._w, sequenz)).split("\n")
        praefix = 'if {"[%s ' % kennung
        rest = "\n".join(z for z in zeilen if not z.startswith(praefix))
        widget.tk.call("bind", widget._w, sequenz, rest)
    except tk.TclError:
        pass
    try:
        widget.deletecommand(kennung)
    except tk.TclError:
        pass


def an_toplevel_binden(besitzer: tk.Misc, sequenz: str, funktion: Callable[..., Any]) -> "str | None":
    """Bindet ``funktion`` an das Toplevel von ``besitzer`` und nimmt die Bindung beim Zerstoeren von ``besitzer`` ab."""
    try:
        oben = besitzer.winfo_toplevel()
        kennung = oben.bind(sequenz, funktion, add="+")
    except tk.TclError:
        return None

    def _abnehmen(e: Any, _o=oben, _s=sequenz, _k=kennung, _b=besitzer) -> None:
        if e.widget is _b:
            bindung_loesen(_o, _s, _k)

    besitzer.bind("<Destroy>", _abnehmen, add="+")
    return kennung
