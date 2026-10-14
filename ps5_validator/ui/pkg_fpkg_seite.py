# -*- coding: utf-8 -*-
"""Aufgabe 7 "PKG / FPKG" als Seite im rechten Bereich der Ansicht UMWANDELN (seit 12.10.2026).

Bis zum 12.10.2026 abends war das nur ein Platzhalter (kein QUELLE-, ZIEL- oder ZIELFORMAT-Feld, kein AUFTRAG -
die Funktionen standen noch nicht fest). Jetzt zeigt die Seite oben zwei Knoepfe, **PKG** und **FPKG**, darunter
eine von zwei eingebetteten Seiten:

* **PKG** - :mod:`ps5_validator.ui.ps4_dump_image` (bis dahin das Fenster "PS4 PKG Dump & Image Converter").
* **FPKG** - :mod:`ps5_validator.ui.ps5_pkg_fenster` (bis dahin das Fenster "PS5 PKG Dump & Image Converter").

Beide Module bauen seit demselben Tag ihr ``self.win`` als ``tk.Frame`` statt als eigenes Popup-Fenster (siehe
ihre eigenen Modul-Docstrings) - diese Seite reicht ihnen beim ersten Zeigen ihren Inhaltsrahmen (``self.inhalt``)
als ``master`` herein und baut sie dadurch direkt an ihren Platz; danach wird nur noch ein- und ausgeblendet
(``pack``/``pack_forget``), kein Neuaufbau. Beide bleiben Singletons (``ps4_dump_image.FENSTER_ATTRIBUT`` /
``ps5_pkg_fenster.FENSTER_ATTRIBUT`` auf ``gui``) - die Bibliothek reicht ein umzuwandelndes Paket weiterhin ueber
``PS5ConverterGUI._show_ps4_pkg_converter`` herein, die jetzt zuerst diese Seite zeigt und dann "PKG" erzwingt.

Gleicher Grundmechanismus wie :mod:`ampr_seite`: eine eigene Flaeche in der Zelle (1, 1), die die Rollflaeche mit
den Aufgabenkarten ersetzt (``PS5ConverterGUI._pkg_fpkg_seite_einblenden``).
"""
from __future__ import annotations

import sys
import tkinter as tk

from ps5_validator.ui import ps4_dump_image
from ps5_validator.ui import ps5_pkg_fenster

SEITE_ATTRIBUT = "_pkg_fpkg_seite"

UNTERSEITE_PKG = "pkg"
UNTERSEITE_FPKG = "fpkg"


def _haupt(gui):
    """Das Modul des Hauptprogramms (``pt``, Schriften, ``RoundedButton``)."""
    return sys.modules[type(gui).__module__]


class PkgFpkgSeite:
    """Die Seite: oben die Wahl zwischen PKG und FPKG, darunter die gewaehlte eingebettet."""

    def __init__(self, gui) -> None:
        self.g = gui
        self.h = _haupt(gui)
        self.t = gui._t
        self.c = gui._COLORS
        self.unterseite = ""
        self._sichtbar: "tk.Frame | None" = None
        #: Das Objekt der sichtbaren Unterseite - liefert sie ``quelle_karte``, steht der PKG-Knopf buendig darueber.
        self._aktiv = None
        self.knoepfe: "dict[str, object]" = {}
        self._bauen()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _bauen(self) -> None:
        g, h, c, t = self.g, self.h, self.c, self.t
        F, pt = h.UI_SCHRIFT, h.pt
        self.rahmen = tk.Frame(g.root, bg=c["bg_main"], padx=24, pady=18)

        # Ohne Ueberschrift "PKG / FPKG" (Nutzer 14.10.2026: die Seite heisst schon so in der Seitenleiste); die zwei
        # Knoepfe sind groesser und der erste steht buendig ueber der Karte QUELLE (:meth:`_reihe_ausrichten`).
        reihe = tk.Frame(self.rahmen, bg=c["bg_main"])
        reihe.pack(fill="x")
        self._reihe = reihe
        for kennung, befehl in ((UNTERSEITE_PKG, self._pkg_knopf_gedrueckt),
                                (UNTERSEITE_FPKG, self._fpkg_knopf_gedrueckt)):
            knopf = h.RoundedButton(
                reihe, text="", command=befehl,
                font=(F, pt(13), "bold"), bg=c["console_bg"], fg=c["fg_secondary"],
                activebackground=c["fg_accent"], activeforeground=c["bg_main"],
                outline=c["border"], radius=8, height=46, pille=True, breite_nach_text=True, polster_x=28)
            knopf.pack(side="left", padx=(0, 10))
            self.knoepfe[kennung] = knopf

        self.inhalt = tk.Frame(self.rahmen, bg=c["bg_main"])
        self.inhalt.pack(fill="both", expand=True, pady=(14, 0))
        self.inhalt.bind("<Configure>", lambda _e: self._reihe_ausrichten(), add="+")
        self._knoepfe_zeichnen()

    def _reihe_ausrichten(self) -> None:
        """Schiebt die Knopfreihe so, dass "PKG" links buendig mit der Karte QUELLE der Unterseite steht.

        Die Unterseite FPKG hat links eine Leiste (Umwandeln, Bibliothek, Optionen); ohne Ausgleich stuende "PKG" ueber
        der Leiste statt ueber der Karte. Eine Unterseite ohne ``quelle_karte`` (PKG) bekommt keinen Versatz.
        """
        knopf = self.knoepfe.get(UNTERSEITE_PKG)
        karte = getattr(self._aktiv, "quelle_karte", None)
        if karte is not None and not getattr(karte, "_reihe_gebunden", False):
            # Die Karte wird erst nach der Seite sichtbar und wandert mit der Fensterbreite: dann neu ausrichten.
            karte.bind("<Configure>", lambda _e: self._reihe_ausrichten(), add="+")
            karte._reihe_gebunden = True
        try:
            jetzt = int(self._reihe.pack_info().get("padx", 0) or 0)
        except (tk.TclError, TypeError, ValueError):
            jetzt = 0
        try:
            if karte is None or knopf is None or not karte.winfo_ismapped():
                ziel = 0
            else:
                # Sichtbar ist die runde Huelle der Karte (pw.Karte), nicht ihr Innenrahmen - an ihr ausrichten.
                kante = getattr(karte, "_huelle", karte)
                ziel = max(0, jetzt + kante.winfo_rootx() - knopf.winfo_rootx())
            if ziel != jetzt:
                self._reihe.pack_configure(padx=(ziel, 0))
        except tk.TclError:
            pass

    def _knopf_text(self, kennung: str) -> str:
        return self.t("pkg_fpkg_seite.tab_pkg" if kennung == UNTERSEITE_PKG else "pkg_fpkg_seite.tab_fpkg")

    def _knoepfe_zeichnen(self) -> None:
        """Hebt die gewaehlte Unterseite hervor - farbig UND mit Haken (nicht nur ueber die Farbe)."""
        c = self.c
        for kennung, knopf in self.knoepfe.items():
            beschriftung = self._knopf_text(kennung)
            gewaehlt = kennung == self.unterseite
            knopf.config(text=("✓ " + beschriftung) if gewaehlt else beschriftung,
                         bg=c["fg_accent"] if gewaehlt else c["console_bg"],
                         fg=c["bg_main"] if gewaehlt else c["fg_secondary"])

    def _pkg_knopf_gedrueckt(self) -> None:
        self.pkg_zeigen()

    def _fpkg_knopf_gedrueckt(self) -> None:
        self.fpkg_zeigen()

    # ------------------------------------------------------------------
    # Unterseiten
    # ------------------------------------------------------------------
    def _umschalten(self, kennung: str, win: "tk.Frame") -> None:
        if self._sichtbar is not None and self._sichtbar is not win:
            self._sichtbar.pack_forget()
        if win.winfo_manager() != "pack":
            win.pack(fill="both", expand=True)
        self._sichtbar = win
        self.unterseite = kennung
        self._knoepfe_zeichnen()

    def pkg_zeigen(self, vorgabe: str = "") -> None:
        """Zeigt "PKG" (``ps4_dump_image``) - eine Vorgabe (aus der Bibliothek) wird gleich eingelesen."""
        h = self.h
        fenster = ps4_dump_image.oeffnen(self.g, h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt, vorgabe, master=self.inhalt)
        kam_von_fpkg = self.unterseite == UNTERSEITE_FPKG
        self._aktiv = fenster
        self._umschalten(UNTERSEITE_PKG, fenster.win)
        self.rahmen.after_idle(self._reihe_ausrichten)
        if kam_von_fpkg:
            # Die Angaben des FPKG-Pakets in Seitenleiste und Info-Box gehoeren nicht zu "PKG".
            ps5_pkg_fenster.spielinfo_zuruecksetzen(self.g)

    def fpkg_zeigen(self, vorgabe: str = "") -> None:
        """Zeigt "FPKG" (``ps5_pkg_fenster``)."""
        h = self.h
        fenster = ps5_pkg_fenster.oeffnen(self.g, h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt, vorgabe, master=self.inhalt)
        self._aktiv = fenster
        self._umschalten(UNTERSEITE_FPKG, fenster.win)
        fenster.spielinfo_nachziehen()
        self.rahmen.after_idle(self._reihe_ausrichten)


def seite(gui) -> PkgFpkgSeite:
    """Die Seite des Programms - beim ersten Zeigen gebaut."""
    vorhanden = getattr(gui, SEITE_ATTRIBUT, None)
    if vorhanden is None:
        vorhanden = PkgFpkgSeite(gui)
        setattr(gui, SEITE_ATTRIBUT, vorhanden)
    return vorhanden


def zeigen(gui) -> PkgFpkgSeite:
    """Blendet die Seite im rechten Bereich ein. Nur beim allerersten Mal waehlt sie "PKG" von selbst - ein
    spaeterer Aufruf (ein erneuter Druck auf "7.") laesst die zuletzt gewaehlte Unterseite stehen."""
    s = seite(gui)
    gui._pkg_fpkg_seite_einblenden(s.rahmen)
    if not s.unterseite:
        s.pkg_zeigen()
    return s
