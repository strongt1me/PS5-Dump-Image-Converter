# -*- coding: utf-8 -*-
"""Der Fortschrittsbalken der Knopfleiste des Hauptfensters - mit runden Ecken auf dem Bild der Leiste.

Nutzerwunsch 17.11.2026 (mit Bild des Balkens): "hier bitte die Ecken abrunden". Bis dahin war es ein ``ttk.Progressbar`` mit
rechteckiger Rinne. Die anderen Fenster haben seit v1.9.62 einen Balken mit runden Enden (``fenster_pillen.Progressbar``);
er steht dort auf einer einfarbigen Flaeche. Die Knopfleiste liegt aber auf dem Hintergrundbild: Hinter den Rundungen darf
keine Flaechenfarbe stehen, sondern das Bild an dieser Stelle - wie bei den Pillen STARTEN und ABBRECHEN
(``RoundedButton(hintergrund=...)``). Dieser Balken zeichnet seine Rundungen deshalb ueber den Bildausschnitt, den das
Hauptfenster liefert (``PS5ConverterGUI._rund_hintergrund``).
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Optional

from PIL import Image

from ps5_validator.ui import fenster_pillen


class LeistenBalken(fenster_pillen.Progressbar):
    """``fenster_pillen.Progressbar`` ueber dem Bildausschnitt der Flaeche, auf der er steht.

    Args:
        hintergrund: ``(widget, breite, hoehe) -> PIL-Bild | None`` - was hinter dem Balken liegt
            (``_rund_hintergrund`` des Hauptfensters); ``None`` heisst: keine Flaeche mit Bild, die Rundungen
            stehen auf der Grundfarbe des Elternteils.
        hoehe: Hoehe in Entwurfspunkten (wird mit der Anzeigeskalierung vergroessert).
    """

    def __init__(self, master, look, hintergrund: "Optional[Callable[[Any, int, int], Optional[Image.Image]]]" = None,
                 hoehe: float = 22, **opt: Any) -> None:
        self._hintergrund = hintergrund
        #: ``((breite, hoehe, x, y), Bild)`` - der Ausschnitt wird nur neu geholt, wenn sich Groesse oder Lage aendern
        #: (der Balken zeichnet sich bei jedem Fortschrittswert neu).
        self._ausschnitt_merker: "Optional[tuple]" = None
        super().__init__(master, look, **opt)
        tk.Canvas.configure(self, height=look.z.px(hoehe))

    def _ausschnitt(self, b: int, h: int) -> "Optional[Image.Image]":
        """Der Bildausschnitt hinter dem Balken (``None`` ohne Bild); gemerkt, solange Groesse und Lage gleich bleiben."""
        if not callable(self._hintergrund):
            return None
        try:
            lage = (b, h, int(self.winfo_rootx()), int(self.winfo_rooty()))
        except tk.TclError:
            return None
        if self._ausschnitt_merker is not None and self._ausschnitt_merker[0] == lage:
            return self._ausschnitt_merker[1]
        try:
            grund = self._hintergrund(self, b, h)
        except Exception:  # noqa: BLE001 - ohne Ausschnitt steht der Balken auf der Grundfarbe, er faellt nicht aus
            grund = None
        self._ausschnitt_merker = (lage, grund)
        return grund

    def _bild(self, b: int, h: int) -> "Image.Image":
        bild = super()._bild(b, h)
        grund = self._ausschnitt(b, h)
        if grund is None:
            return bild
        unten = grund.convert("RGBA")
        if unten.size != (b, h):
            unten = unten.resize((b, h))
        unten.alpha_composite(bild)
        return unten

    def nachziehen(self) -> None:
        """Holt den Hintergrund neu und zeichnet - nach Verschieben, Design- oder Bildwechsel (``_runde_flaechen_jetzt``)."""
        self._ausschnitt_merker = None
        self._zeichnen()
