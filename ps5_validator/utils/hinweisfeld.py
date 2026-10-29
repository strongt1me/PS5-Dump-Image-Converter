# -*- coding: utf-8 -*-
"""Grauer Hinweistext in einem leeren Eingabefeld (``ttk.Entry`` kennt keinen Platzhalter).

Ueber das Feld legt sich ein Etikett als Kind des Feldes. Es steht nur da, solange die Variable leer ist und das
Feld nicht den Fokus hat; ein Klick darauf setzt den Fokus ins Feld. Die Variable bleibt dabei unberuehrt - der
Hinweis ist kein Inhalt, den ein Lauf versehentlich als Pfad lesen koennte.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable

logger = logging.getLogger("PS5Converter.hinweisfeld")

_FALLBACK_GRAU = "#8a8f98"


class Hinweisfeld:
    """Haengt einen Hinweistext an ein ``ttk.Entry``.

    Args:
        feld: das Eingabefeld.
        variable: seine ``textvariable``.
        text: liefert den aktuellen Hinweis (wechselt mit Aufgabe und Sprache); leer = kein Hinweis.
    """

    def __init__(self, feld: ttk.Entry, variable: tk.StringVar, text: Callable[[], str]) -> None:
        self.feld = feld
        self.variable = variable
        self._text = text
        self.etikett = tk.Label(feld, anchor="w", borderwidth=0, padx=4, cursor="xterm")
        self.etikett.bind("<Button-1>", lambda _e: self.feld.focus_set())
        self.feld.bind("<FocusIn>", self._fokus_rein, add="+")
        self.feld.bind("<FocusOut>", lambda _e: self.aktualisieren(), add="+")
        self.variable.trace_add("write", lambda *_a: self.aktualisieren())
        self.aktualisieren()

    def _fokus_rein(self, _event=None) -> None:
        self.etikett.place_forget()

    def _farben(self) -> tuple[str, str]:
        try:
            stil = ttk.Style(self.feld)
            grund = stil.lookup("TEntry", "fieldbackground") or stil.lookup("TEntry", "background") or "white"
            grau = stil.lookup("TEntry", "foreground", ["disabled"]) or _FALLBACK_GRAU
            return str(grund), str(grau)
        except Exception:  # noqa: BLE001
            return "white", _FALLBACK_GRAU

    def aktualisieren(self) -> None:
        """Zeigt oder verbirgt den Hinweis und zieht Text und Farben nach (Aufgabe, Sprache, Design)."""
        try:
            text = str(self._text() or "")
            leer = not str(self.variable.get() or "").strip()
            hat_fokus = self.feld.focus_get() is self.feld
            if not (text and leer) or hat_fokus:
                self.etikett.place_forget()
                return
            grund, grau = self._farben()
            self.etikett.configure(text=text, background=grund, foreground=grau, font=self.feld.cget("font"))
            self.etikett.place(x=2, y=2, relwidth=1.0, relheight=1.0, width=-4, height=-4)
            self.etikett.lift()
        except tk.TclError:
            pass   # Fenster schon zerstoert
        except Exception as exc:  # noqa: BLE001
            logger.debug("Hinweisfeld nicht aktualisiert: %s", exc)
