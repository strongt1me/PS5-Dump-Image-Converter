# -*- coding: utf-8 -*-
"""Das Fenster "PKG-Extras" unter WEITERE TOOLS (Nutzerwunsch 30.10.2026).

Die vier Werkzeuge der frueheren Seite "Extras" der FPKG-Ansicht - DDS zu PNG, exFAT-Boot-Sektor reparieren,
exFAT-Inhalt entpacken/aufbauen, FFPKG-Metadaten reparieren - haben dort keinen Reiter mehr und liegen seitdem in einem
eigenen Fenster. Die Karten und ihre Handler sind dieselben wie vorher: :class:`PkgExtras` erbt sie von
:class:`ps5_validator.ui.ps5_pkg_fenster.Ps5PkgFenster` und baut sie ueber ``_seite_extras`` in ein eigenes Toplevel,
ohne die uebrige Oberflaeche des PKG-Fensters (Paketliste, Faeden, Takt) zu erzeugen. Das Fenster haengt deshalb nicht von
einem geoeffneten PKG-Bereich ab.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from ps5_validator.ui import ps5_pkg_fenster as fz


class PkgExtras(fz.Ps5PkgFenster):
    """Nur die Teile der FPKG-Seite, die die vier Karten brauchen (``g``, ``t``, ``c``, ``F``, ``pt``, ``win``)."""

    def __init__(self, gui, win: "tk.Toplevel", schrift: str, mono: str, pt: Callable[[int], int]) -> None:
        # Bewusst ohne ``super().__init__()``: Das wuerde die ganze FPKG-Seite samt Takt und Faeden bauen.
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.win = win
        seite = tk.Frame(win, bg=self.c["bg_main"])
        seite.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self._seite_extras(seite, mit_kopf=False)


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int]) -> "tk.Toplevel":
    """Baut das Fenster und gibt es zurueck (das Menue oeffnet und schliesst es ueber ``_werkzeugknopf``)."""
    titel = gui._t("titlebar.pkg_extras")
    win = gui._build_modern_toplevel(titel, 780, 720, min_width=640, min_height=480)
    gui._build_modern_header(win, titel, gui._t("pkgextras.subtitle"))
    PkgExtras(gui, win, schrift, mono, pt)         # die Knoepfe halten ihn ueber ihre Befehle am Leben
    return win
