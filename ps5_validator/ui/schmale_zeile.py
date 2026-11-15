# -*- coding: utf-8 -*-
"""Eine Rasterzeile "Feld links, Knoepfe rechts", die bei Platzmangel die Knoepfe in eine zweite Reihe setzt.

Gefunden am 15.11.2026 beim Durchmessen aller Seiten bei 150 % und 200 % Windows-Skalierung: Auf der Seite
"Y2JB Updater" steht in jeder Karte eine Klappliste mit zwei Knoepfen daneben (``Fassungen laden``,
``Herunterladen``). Die Knoepfe wachsen mit der Skalierung (``knopfmass``), die Klappliste bekommt, was
uebrig bleibt - bei 200 % auf einem 1920er Schirm 26 statt 329 Pixel. Eine Liste, in der man nichts lesen kann.

Die Regel: Passt das Feld in seiner natuerlichen Breite samt Knoepfen in die Zeile, bleibt alles in einer Reihe
(das Bild bei 125 % aendert sich nicht). Sonst bekommt das Feld die ganze Breite, und die Knoepfe stehen darunter.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Sequence

logger = logging.getLogger("PS5Converter.ui.schmale_zeile")


def zeile_umbrechen(zeile: "tk.Misc", feld: "tk.Misc", knoepfe: Sequence["tk.Misc"], abstand: int = 8,
                    oben: int = 6, mindestbreite: int = 0, rechts: bool = False) -> "callable":
    """Haengt die Umbruchregel an eine Rasterzeile.

    Vorausgesetzt: ``feld`` steht in Spalte 0 und ``knoepfe`` in den Spalten 1, 2 ... derselben Rasterzeile (``zeile``,
    Reihe 0); Spalte 0 hat Gewicht 1. Nach dem Umbruch steht ``feld`` ueber allen Spalten, der erste Knopf links
    darunter und der letzte rechts.

    Args:
        zeile: Der Rahmen, dessen Breite entscheidet.
        feld: Das Eingabefeld oder die Klappliste.
        knoepfe: Die Knoepfe rechts davon, von links nach rechts.
        abstand: Luecke zwischen den Teilen in einer Reihe (Pixel).
        oben: Luecke ueber der zweiten Reihe.
        mindestbreite: Die Breite, die das Feld in einer Reihe mindestens haben soll. Ohne Angabe gilt seine
            natuerliche Breite (``winfo_reqwidth``) - bei einem Text, der sich selbst umbricht (Statuszeile), ist
            die keine brauchbare Messgroesse, dort wird die gewuenschte Mindestbreite angegeben.
        rechts: Nach dem Umbruch steht auch der erste Knopf rechtsbuendig (statt links) - fuer eine Fusszeile mit
            einem einzigen Knopf.

    Returns:
        Die Anordnungsfunktion (ohne Argumente aufrufbar) - fuer Tests und fuer ein erzwungenes Neuanordnen.
    """
    knoepfe = list(knoepfe)
    zustand = {"gestapelt": None}

    def _anordnen(_ereignis=None) -> None:
        try:
            breite = int(zeile.winfo_width())
            if breite <= 1:
                return                                   # noch nicht angelegt
            noetig = (int(mindestbreite) or int(feld.winfo_reqwidth())) \
                + sum(int(k.winfo_reqwidth()) + abstand for k in knoepfe)
        except tk.TclError:
            return
        stapeln = breite < noetig
        if stapeln == zustand["gestapelt"]:
            return
        zustand["gestapelt"] = stapeln
        try:
            if stapeln:
                feld.grid_configure(row=0, column=0, columnspan=len(knoepfe) + 1, padx=0)
                for i, knopf in enumerate(knoepfe):
                    # Der erste Knopf links unter dem Feld, die uebrigen in ihren Spalten, der letzte rechtsbuendig.
                    links = i == 0 and not rechts
                    knopf.grid_configure(row=1, column=0 if links else i + 1, columnspan=1,
                                         sticky="w" if links else ("e" if i == len(knoepfe) - 1 else ""),
                                         padx=0, pady=(oben, 0))
            else:
                feld.grid_configure(row=0, column=0, columnspan=1, padx=(0, abstand))
                for i, knopf in enumerate(knoepfe):
                    knopf.grid_configure(row=0, column=i + 1, columnspan=1, sticky="",
                                         padx=(0, abstand) if i < len(knoepfe) - 1 else 0, pady=0)
        except tk.TclError as exc:
            logger.debug("Zeile nicht umbrechbar: %s", exc)

    zeile.bind("<Configure>", _anordnen, add="+")
    try:
        zeile.after_idle(_anordnen)
    except tk.TclError:
        pass
    return _anordnen


def knoepfe_unter_liste(zeile: "tk.Misc", knopfblock: "tk.Misc", feld: "tk.Misc", erstes: "tk.Misc",
                        mindestbreite: int, abstand: int = 8, oben: int = 6) -> "callable":
    """Pack-Variante von :func:`zeile_umbrechen`: Der Knopfblock steht rechts, bei Platzmangel unter der Zeile.

    Gedacht fuer die Zeile "Beschriftung - Liste - Knoepfe" (``side="left"``, ``side="left"``, ``side="right"``):
    Die Liste darf zuerst nachgeben, aber nicht auf einen Streifen schrumpfen. Gefunden am 15.11.2026 in der
    Bibliothek (Scan-Ordner): Im kleinsten Fenster (1260 px, 125 %) blieben der Liste 6 Pixel.

    Voraussetzung: ``erstes`` (die Beschriftung), ``knopfblock`` und ``feld`` sind in dieser Reihenfolge Kinder von
    ``zeile``; ``knopfblock`` steht (wie bisher) ``side="right"`` **vor** ``feld``.

    Args:
        zeile: Der Rahmen, dessen Breite entscheidet.
        knopfblock: Der Rahmen mit den Knoepfen.
        feld: Die Liste (bekommt in der Reihe, was uebrig bleibt).
        erstes: Das zuerst gepackte Element (die Beschriftung): Der Knopfblock wird in der unteren Reihe **vor** ihm
            gepackt, damit er die ganze Breite unter allem bekommt.
        mindestbreite: Die Breite, die die Liste in einer Reihe mindestens haben soll.
        abstand: Luecke links vom Knopfblock in der Reihe (Pixel).
        oben: Luecke ueber dem Knopfblock in der unteren Reihe.

    Returns:
        Die Anordnungsfunktion (ohne Argumente aufrufbar) - fuer Tests.
    """
    zustand = {"unten": None}

    def _anordnen(_ereignis=None) -> None:
        try:
            breite = int(zeile.winfo_width())
            if breite <= 1:
                return
            noetig = (int(erstes.winfo_reqwidth()) + 8 + int(mindestbreite)
                      + int(knopfblock.winfo_reqwidth()) + abstand)
        except tk.TclError:
            return
        unten = breite < noetig
        if unten == zustand["unten"]:
            return
        zustand["unten"] = unten
        try:
            knopfblock.pack_forget()
            if unten:
                knopfblock.pack(side="bottom", anchor="e", padx=0, pady=(oben, 0), before=erstes)
            else:
                knopfblock.pack(side="right", padx=(abstand, 0), before=feld)
        except tk.TclError as exc:
            logger.debug("Knopfblock nicht umsetzbar: %s", exc)

    zeile.bind("<Configure>", _anordnen, add="+")
    try:
        zeile.after_idle(_anordnen)
    except tk.TclError:
        pass
    return _anordnen


def hinweise_bei_platzmangel_ausblenden(seite: "tk.Misc", hinweise: Sequence[tuple]) -> "callable":
    """Blendet erklaerende Hinweisabsaetze aus, solange die Seite sonst ueber den unteren Rand hinausragt.

    Gebraucht, weil der Umbruch der Reihe (:func:`zeile_umbrechen`) und die umbrechende Schritt-Ueberschrift eine Karte
    hoeher machen: Im kleinsten Fenster (1260x700, 125 %) schob das die Knoepfe "Hochladen" ganz aus dem Bild, vorher
    standen sie wenigstens halb darin (Bildschirmfoto vom 15.11.2026). Die Seite hat keinen Rollbalken (Nutzerwunsch),
    also gibt sie zuerst her, was nur erklaert: Dasselbe Vorgehen steht in ``_konsole_tafel_kompakt`` (Unterzeile und
    Protokollzeilen).

    Aus, wenn der Platzbedarf der Seite (``winfo_reqheight``) ihre Hoehe uebersteigt; wieder an, wenn er mit den
    Hinweisen zurueck hineinpasst. Ein Zurueck, das gleich wieder ausgeblendet wuerde, wird bei dieser Hoehe nicht
    noch einmal versucht (kein Flackern).

    Args:
        seite: Die Seite (ihre Hoehe entscheidet).
        hinweise: Paare ``(Label, Anker)``: der Hinweis (gepackt) und das Element, **hinter** dem er wieder
            eingesetzt wird.

    Returns:
        Die Pruefung (ohne Argumente aufrufbar) - fuer Tests.
    """
    hinweise = [(h, a) for h, a in hinweise]
    zustand = {"aus": False, "frei": 0, "infos": [], "gesperrt_bei": 0}

    def _pruefen(_ereignis=None) -> None:
        try:
            hoch = int(seite.winfo_height())
            if hoch <= 1:
                return
            bedarf = int(seite.winfo_reqheight())
            if not zustand["aus"] and bedarf > hoch:
                zustand["infos"] = []
                for hinweis, _anker in hinweise:
                    info = dict(hinweis.pack_info())
                    info.pop("in", None)
                    zustand["infos"].append(info)
                    hinweis.pack_forget()
                seite.update_idletasks()
                zustand["frei"] = max(0, bedarf - int(seite.winfo_reqheight()))
                zustand["aus"] = True
            elif zustand["aus"] and hoch > zustand["gesperrt_bei"] and bedarf + zustand["frei"] + 4 <= hoch:
                for (hinweis, anker), info in zip(hinweise, zustand["infos"]):
                    hinweis.pack(after=anker, **info)
                zustand["aus"] = False
                seite.update_idletasks()
                if int(seite.winfo_reqheight()) > hoch:      # doch zu hoch: wieder weg und bei dieser Hoehe nicht erneut
                    zustand["gesperrt_bei"] = hoch
                    for hinweis, _anker in hinweise:
                        hinweis.pack_forget()
                    zustand["aus"] = True
        except tk.TclError as exc:
            logger.debug("Hinweise nicht ein-/ausblendbar: %s", exc)

    def _geplant(_ereignis=None) -> None:
        """Pruefen, nachdem die Umbrueche der Texte sich gesetzt haben (sie ziehen die Hoehe erst nachtraeglich nach).

        Die Seite selbst aendert dabei ihre Groesse nicht mehr - es kaeme kein weiteres ``<Configure>``. Darum zwei
        verzoegerte Pruefungen nach jedem Ereignis, die jeweils die vorige ersetzen.
        """
        try:
            for schluessel in ("t1", "t2"):
                if zustand.get(schluessel):
                    seite.after_cancel(zustand[schluessel])
            zustand["t1"] = seite.after(120, _pruefen)
            zustand["t2"] = seite.after(450, _pruefen)
        except tk.TclError:
            pass

    seite.bind("<Configure>", _geplant, add="+")
    _geplant()
    return _pruefen
