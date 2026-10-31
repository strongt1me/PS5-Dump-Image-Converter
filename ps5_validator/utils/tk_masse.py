"""Tk-Masse als Pixelzahl lesen - fest unter Tk 8.6 und Tk 9.

``cget("width")`` liefert bei nie gesetztem Wert die Vorgabe in
Bildschirmeinheiten (``"10c"``, ``"7c"``), ``float()`` darauf wirft einen
ValueError. ``winfo_fpixels`` wandelt Zahl und Einheit (c, i, m, p) in Pixel.
"""
from __future__ import annotations


def pixel(widget, wert, vorgabe: float = 0.0) -> float:
    """Wandelt ``wert`` (Zahl, Zahlentext oder Text mit Einheit) in Pixel."""
    if wert in (None, ""):
        return float(vorgabe)
    try:
        return float(wert)
    except (TypeError, ValueError):
        pass
    try:
        return float(widget.winfo_fpixels(str(wert)))
    except Exception:
        return float(vorgabe)


def pixel_ganz(widget, wert, vorgabe: int = 0) -> int:
    """Wie :func:`pixel`, auf ganze Pixel gerundet."""
    return int(round(pixel(widget, wert, vorgabe)))


def cget_pixel(widget, option: str, vorgabe: int = 0) -> int:
    """``widget.cget(option)`` als ganze Pixelzahl."""
    return pixel_ganz(widget, widget.cget(option), vorgabe)
