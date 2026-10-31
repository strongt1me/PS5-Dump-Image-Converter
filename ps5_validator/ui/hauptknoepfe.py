# -*- coding: utf-8 -*-
"""STARTEN und ABBRECHEN der Seite 7 (PKG / FPKG) wie bei den Aufgaben 1 bis 6.

Die Aufgaben 1 bis 6 haben zwei grosse Knoepfe (``run_btn``/``abort_btn`` des Hauptprogramms: ``RoundedButton``,
48 px hoch, 190/170 px breit, 13 pt fett, Verlauf beziehungsweise rot gesperrt-grau). Die Bereiche PS4 PKG und PS5 PKG
bauten stattdessen kleine Pillen (``pw.Button``). Hier entstehen dieselben Knoepfe wie bei Aufgabe 1, mit den Methoden,
die die beiden Bereiche von ihren Knoepfen kennen (``configure(state=..., text=...)``, ``state([...])``).
"""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable

_KLASSEN: "dict[type, type]" = {}


def _klasse(basis: type) -> type:
    """``RoundedButton`` des Hauptprogramms, dazu ``state``/``instate`` wie bei ``ttk.Button`` (einmal je Basisklasse)."""
    klasse = _KLASSEN.get(basis)
    if klasse is None:
        class Hauptknopf(basis):                                # type: ignore[misc, valid-type]
            def state(self, zustaende: Any = None) -> tuple:
                if zustaende is not None:
                    for eintrag in ([zustaende] if isinstance(zustaende, str) else list(zustaende)):
                        if eintrag == "disabled":
                            self.configure(state="disabled")
                        elif eintrag == "!disabled":
                            self.configure(state="normal")
                return ("disabled",) if str(self.cget("state")) == "disabled" else ()

            def instate(self, zustaende: Any, befehl: "Callable | None" = None) -> Any:
                liste = [zustaende] if isinstance(zustaende, str) else list(zustaende)
                gesperrt = str(self.cget("state")) == "disabled"
                passt = all((gesperrt if e == "disabled" else not gesperrt) for e in liste
                            if e in ("disabled", "!disabled"))
                if passt and befehl is not None:
                    return befehl()
                return passt

        klasse = Hauptknopf
        _KLASSEN[basis] = klasse
    return klasse


def verfuegbar(gui) -> bool:
    haupt = sys.modules.get(type(gui).__module__)
    return haupt is not None and hasattr(haupt, "RoundedButton") and hasattr(haupt, "bibliothek_zeichnen")


def starten_abbrechen(gui, eltern, start_text: str, start_befehl, abbrechen_befehl) -> "tuple[Any, Any] | None":
    """Baut STARTEN und ABBRECHEN wie ``run_btn``/``abort_btn``. ``None``, wenn das Hauptprogramm sie nicht kennt (Tests)."""
    if not verfuegbar(gui):
        return None
    h = sys.modules[type(gui).__module__]
    c = gui._COLORS
    klasse = _klasse(h.RoundedButton)
    gesperrt = h.bibliothek_zeichnen.knopf_farben(c, "flaeche", "gesperrt")
    schrift = (h.UI_SCHRIFT, h.pt(13), "bold")
    breite = 190
    try:
        # Ein langer Text (``Umwandlung starten``) bekommt mehr Platz als die 190 px der Aufgabe 1.
        noetig = tkfont.Font(root=eltern, font=schrift).measure(str(start_text)) + 2 * h.pt(14)
        faktor = max(0.01, float(h.knopfmass(100, eltern)) / 100.0)
        breite = max(breite, int(noetig / faktor) + 1)
    except Exception:                                           # noqa: BLE001
        pass
    start = klasse(
        eltern, text=start_text, command=start_befehl, font=schrift,
        bg=c["accent_btn"], fg="white", activebackground=c["accent_btn_hover"], activeforeground="white",
        disabledbackground=gesperrt["fuellung"], disabledforeground=c["fg_secondary"], disabledoutline=gesperrt["rand"],
        radius=10, height=48, width=breite, pille=True, hintergrund=gui._rund_hintergrund, akzent=True)
    abbrechen = klasse(
        eltern, text=gui._t("action.cancel"), command=abbrechen_befehl, font=schrift,
        bg=c["error_btn"], fg=h.lesbare_schrift(c["error_btn"]), activebackground=c["error_btn_hover"],
        activeforeground=h.lesbare_schrift(c["error_btn_hover"]), disabledbackground=gesperrt["fuellung"],
        disabledforeground=c["fg_secondary"], disabledoutline=gesperrt["rand"],
        radius=10, height=48, width=170, pille=True, hintergrund=gui._rund_hintergrund)
    return start, abbrechen
