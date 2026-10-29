# -*- coding: utf-8 -*-
"""Grauer Hinweistext in einem leeren Eingabefeld (``ttk.Entry`` kennt keinen Platzhalter).

Der Hinweis steht **im Feld selbst**: Solange die Variable leer ist und das Feld nicht den Fokus hat, zeigt das Feld
statt ihrer eine eigene Variable mit dem Hinweis, in gedaempfter Schrift. Sobald das Feld angeklickt wird oder die
Variable einen Wert bekommt (Eintippen, Ablegen, Durchsuchen), steht wieder die echte Variable darin.

Ein Etikett ueber dem Feld taugt nicht: Die runden Felder des Programms sind Bildelemente mit durchsichtigen Ecken,
und ein eckiges Etikett fuellt die Ecken aus (30.10.2026 gemeldet). Die echte Variable bleibt unberuehrt - der
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
        self._hinweis = tk.StringVar(master=feld, value="")
        self.zeigt_hinweis = False
        # Vor der Klassenbindung des Feldes: Ein Klick (auch rechts, "Einfuegen") soll schon in die echte Variable gehen.
        feld.bind("<ButtonPress>", self._fokus_rein, add="+")
        feld.bind("<FocusIn>", self._fokus_rein, add="+")
        feld.bind("<FocusOut>", lambda _e: self.aktualisieren(), add="+")
        self.variable.trace_add("write", lambda *_a: self.aktualisieren())
        self.aktualisieren()

    def _grau(self) -> str:
        try:
            return str(ttk.Style(self.feld).lookup("TEntry", "foreground", ["disabled"]) or _FALLBACK_GRAU)
        except Exception:  # noqa: BLE001
            return _FALLBACK_GRAU

    def _verbergen(self) -> None:
        if not self.zeigt_hinweis:
            return
        self.feld.configure(textvariable=self.variable, foreground="")
        self.zeigt_hinweis = False

    def _fokus_rein(self, _event=None) -> None:
        try:
            self._verbergen()
        except tk.TclError:
            pass   # Fenster schon zerstoert

    def aktualisieren(self) -> None:
        """Zeigt oder verbirgt den Hinweis und zieht Text und Farbe nach (Aufgabe, Sprache, Design)."""
        try:
            text = str(self._text() or "")
            leer = not str(self.variable.get() or "").strip()
            if not (text and leer) or self.feld.focus_get() is self.feld:
                self._verbergen()
                return
            self._hinweis.set(text)
            self.feld.configure(textvariable=self._hinweis, foreground=self._grau())
            self.zeigt_hinweis = True
        except tk.TclError:
            pass   # Fenster schon zerstoert
        except Exception as exc:  # noqa: BLE001
            logger.debug("Hinweisfeld nicht aktualisiert: %s", exc)
