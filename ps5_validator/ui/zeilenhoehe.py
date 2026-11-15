# -*- coding: utf-8 -*-
"""Zeilenhoehe der Listen (``ttk.Treeview``) - an der Schrift gemessen, nicht fest.

Gemeldet von einem Anwender mit Windows-Skalierung 200 % (2880x1800): Im Fenster
ABBILD BEARBEITEN waren die Zeilen der Dateiliste oben und unten abgeschnitten.

Ursache: ``rowheight`` ist eine **Pixelzahl** und bleibt auf jedem Schirm gleich
(24 px), die Schrift der Liste ist aber in **Punkt** angegeben, und ``tk scaling``
rechnet sie in Pixel um. Am 15.11.2026 mit dem Programm-Schriftsatz (Segoe UI,
10 pt) gemessen::

    Skalierung   Textzeile   feste Zeilenhoehe
       100 %       17 px          24 px   (reicht)
       125 %       23 px          24 px   (knapp - hier wurde sie geeicht)
       150 %       28 px          24 px   (abgeschnitten)
       200 %       37 px          24 px   (stark abgeschnitten)

Die Regel hier haelt den Eichpunkt (125 %) und alles darunter unveraendert und
laesst die Zeile darueber mit der Schrift mitwachsen: **nie niedriger als das
eingetragene Mass, nie niedriger als die Textzeile plus ein Pixel Luft** (das ist
das Verhaeltnis, das bei 125 % seit jeher gilt: 23 px Schrift in 24 px Zeile).
Dasselbe Vorgehen steht seit 27.09.2026 in ``_bibliothek_minikante`` (Liste der
Bibliothek) und gilt fuer Knoepfe in ``knopfmass``.

Reine Rechenregel in :func:`zeilenhoehe`; Messen der Schrift in
:func:`schrift_linienhoehe`; beides zusammen in :func:`treeview_zeilenhoehe`.
"""
from __future__ import annotations

import logging
import tkinter as tk
import tkinter.font as tkfont
from typing import Sequence

logger = logging.getLogger("PS5Converter.ui.zeilenhoehe")

#: Pixel, die eine Zeile mindestens ueber der Textzeile der Schrift liegt.
LUFT = 1


def zeilenhoehe(basis: int, linienhoehe: int | None) -> int:
    """Die Zeilenhoehe, die zur gemessenen Textzeile passt.

    Args:
        basis: Das fest eingetragene Mass (Pixel) - die Untergrenze.
        linienhoehe: Hoehe einer Textzeile der Listenschrift in Pixel
            (``linespace``). ``None``, null oder negativ = nicht gemessen.

    Returns:
        ``basis``, wenn die Schrift hineinpasst oder nicht gemessen wurde,
        sonst ``linienhoehe + LUFT``.
    """
    basis = int(basis)
    try:
        gemessen = int(linienhoehe) if linienhoehe is not None else 0
    except (TypeError, ValueError):
        return basis
    if gemessen <= 0:
        return basis
    return max(basis, gemessen + LUFT)


def schrift_linienhoehe(schrift: Sequence | str, widget: "tk.Misc | None" = None) -> int | None:
    """Misst die Hoehe einer Textzeile der Schrift in Pixel (``linespace``).

    Args:
        schrift: Schriftangabe wie bei jedem Bedienelement, z. B.
            ``("Segoe UI", 10)``.
        widget: Ein Bedienelement, ueber dessen Tk-Wurzel gemessen wird. Ohne
            Angabe die Standardwurzel.

    Returns:
        Die Hoehe in Pixel; ``None``, wenn nicht gemessen werden konnte (keine
        Wurzel, ungueltige Schrift) - der Aufrufer behaelt dann sein Mass.
    """
    try:
        wurzel = widget if widget is not None else tk._default_root
        if wurzel is None:
            return None
        return int(tkfont.Font(root=wurzel, font=schrift).metrics("linespace"))
    except Exception as exc:  # noqa: BLE001 - Die Zeilenhoehe darf nie den Aufbau verhindern.
        logger.debug("Zeilenhoehe nicht messbar fuer %r: %s", schrift, exc)
        return None


def treeview_zeilenhoehe(basis: int, schrift: Sequence | str, widget: "tk.Misc | None" = None) -> int:
    """``rowheight`` fuer einen Treeview-Stil: das Mass ``basis``, mitwachsend mit der Schrift."""
    return zeilenhoehe(basis, schrift_linienhoehe(schrift, widget))
