# -*- coding: utf-8 -*-
"""Das Fenster "Geraete im Netz" unter WEITERE TOOLS (14.11.2026; Vorbild: "Nearby" und "Add a device" bei Dump Forge).

Sucht NAS und Rechner, die sich im Netz melden (``utils/geraete_suche.py``: mDNS und WS-Discovery), und zeigt sie mit ihrer Adresse. Ein Geraet mit
Windows-Freigabe (SMB, Rechner) laesst sich als **Quelle** oder **Ziel** waehlen: Das Fenster oeffnet den Ordnerdialog dort (``\\\\Adresse\\``), und der
gewaehlte Ordner steht danach im Feld der Hauptoberflaeche. Das Programm liest und schreibt solche UNC-Pfade ohne Zwischenkopie
(``project_unc_umwandlung``). FTP- und NFS-Geraete werden angezeigt, lassen sich aber nicht als Quelle oder Ziel waehlen.

Die Suche laeuft im eigenen Faden; ihr Ergebnis kommt ueber ``_hauptfaden_planen`` zurueck. Sie kennt keinen Subnetz-Scan: Gefunden wird, was sich selbst meldet.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Any, Callable

from ps5_validator.utils import geraete_suche

logger = logging.getLogger("PS5Converter.geraete_fenster")

#: Wie lange eine Suche hoechstens laeuft (Sekunden).
SUCHZEIT = 4.0
#: Arten, die sich als UNC-Pfad benutzen lassen.
UNC_ARTEN = ("smb", "pc", "wsd")


class GeraeteFenster:
    """Der Inhalt des Fensters: Liste der gefundenen Geraete, Suchen, Quelle oder Ziel waehlen, Adresse kopieren."""

    def __init__(self, gui, win: "tk.Toplevel", schrift: str, pt: Callable[[int], int]) -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.pt = pt
        self.win = win
        self.suche_laeuft = False
        self._abbrechen = False
        self.geraete: "dict[str, geraete_suche.Geraet]" = {}
        self._bauen()
        win.protocol("WM_DELETE_WINDOW", self._schliessen)

    # ---- Aufbau ----------------------------------------------------------------------------------------------
    def _bauen(self) -> None:
        c, pw = self.c, self.g._pw
        koerper = tk.Frame(self.win, bg=c["bg_main"], padx=16, pady=8)
        koerper.pack(fill="both", expand=True)
        koerper.grid_columnconfigure(0, weight=1)
        koerper.grid_rowconfigure(1, weight=1)
        tk.Label(koerper, text=self.t("geraete.hinweis"), font=(self.F, self.pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                 wraplength=700, justify="left", anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.baum = pw.Treeview(koerper, columns=("adresse", "art"), show="tree headings", selectmode="browse", height=12)
        self.baum.heading("#0", text=self.t("geraete.spalte_name"), anchor="w")
        self.baum.heading("adresse", text=self.t("geraete.spalte_adresse"), anchor="w")
        self.baum.heading("art", text=self.t("geraete.spalte_art"), anchor="w")
        self.baum.column("#0", width=220, anchor="w")
        self.baum.column("adresse", width=170, anchor="w")
        self.baum.column("art", width=330, anchor="w")
        self.baum.grid(row=1, column=0, sticky="nsew")
        self.baum.bind("<<TreeviewSelect>>", lambda _e: self._zustand_setzen())

        knoepfe = tk.Frame(koerper, bg=c["bg_main"])
        knoepfe.grid(row=1, column=1, sticky="n", padx=(10, 0))
        self.suchen_knopf = pw.Button(knoepfe, text=self.t("geraete.suchen"), style="Accent.TButton", command=self._suchen)
        self.suchen_knopf.pack(fill="x", pady=(0, 6))
        self.stopp_knopf = pw.Button(knoepfe, text=self.t("geraete.stopp"), command=self._stoppen)
        self.stopp_knopf.pack(fill="x", pady=(0, 14))
        self.quelle_knopf = pw.Button(knoepfe, text=self.t("geraete.als_quelle"), command=lambda: self._waehlen("quelle"))
        self.quelle_knopf.pack(fill="x", pady=(0, 6))
        self.ziel_knopf = pw.Button(knoepfe, text=self.t("geraete.als_ziel"), command=lambda: self._waehlen("ziel"))
        self.ziel_knopf.pack(fill="x", pady=(0, 6))
        self.kopieren_knopf = pw.Button(knoepfe, text=self.t("geraete.adresse_kopieren"), command=self._kopieren)
        self.kopieren_knopf.pack(fill="x", pady=(0, 6))

        self.status_var = tk.StringVar(value=self.t("geraete.status_bereit"))
        tk.Label(koerper, textvariable=self.status_var, font=(self.F, self.pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                 anchor="w", wraplength=700, justify="left").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._zustand_setzen()

    # ---- Zustand ---------------------------------------------------------------------------------------------
    def _gewaehltes(self) -> "geraete_suche.Geraet | None":
        auswahl = self.baum.selection()
        return self.geraete.get(str(auswahl[0])) if auswahl else None

    def _zustand_setzen(self) -> None:
        geraet = self._gewaehltes()
        frei = not self.suche_laeuft
        unc = geraet is not None and geraet.art in UNC_ARTEN
        self.suchen_knopf.config(state="normal" if frei else "disabled")
        self.stopp_knopf.config(state="disabled" if frei else "normal")
        for knopf in (self.quelle_knopf, self.ziel_knopf):
            knopf.config(state="normal" if (unc and frei) else "disabled")
        self.kopieren_knopf.config(state="normal" if geraet is not None else "disabled")

    def _status(self, text: str) -> None:
        self.status_var.set(text)

    # ---- Suchen ----------------------------------------------------------------------------------------------
    def _suchen(self) -> None:
        if self.suche_laeuft:
            return
        self.suche_laeuft = True
        self._abbrechen = False
        for kind in self.baum.get_children(""):
            self.baum.delete(kind)
        self.geraete = {}
        self._status(self.t("geraete.status_suche"))
        self._zustand_setzen()

        def arbeit() -> None:
            try:
                geraete_suche.suchen(SUCHZEIT, melden=lambda g: self.g._hauptfaden_planen(lambda g=g: self._gefunden(g)),
                                     abbruch=lambda: self._abbrechen)
            except Exception as exc:  # noqa: BLE001 - die Suche darf das Fenster nie mitnehmen
                logger.debug("Geraetesuche fehlgeschlagen: %s", exc)
            self.g._hauptfaden_planen(self._suche_beendet)

        threading.Thread(target=arbeit, name="geraete-suche", daemon=True).start()

    def _art_text(self, art: str) -> str:
        return self.t("geraete.art_" + art)

    def _gefunden(self, geraet: "geraete_suche.Geraet") -> None:
        if not self.g._fenster_lebt(self.win):
            return
        iid = "%s|%s" % (geraet.art, geraet.adresse)
        if iid in self.geraete:
            return
        self.geraete[iid] = geraet
        self.baum.insert("", "end", iid=iid, text=geraet.name, values=(geraet.adresse, self._art_text(geraet.art)))
        self._status(self.t("geraete.status_suche_n", n=len(self.geraete)))

    def _suche_beendet(self) -> None:
        if not self.g._fenster_lebt(self.win):
            return
        self.suche_laeuft = False
        self._status(self.t("geraete.status_fertig", n=len(self.geraete)) if self.geraete else self.t("geraete.status_keine"))
        self._zustand_setzen()

    def _stoppen(self) -> None:
        self._abbrechen = True

    # ---- Waehlen und Kopieren --------------------------------------------------------------------------------
    def _waehlen(self, rolle: str) -> None:
        geraet = self._gewaehltes()
        if geraet is None or geraet.art not in UNC_ARTEN:
            self._status(self.t("geraete.nur_freigaben"))
            return
        ordner = filedialog.askdirectory(parent=self.win, initialdir=geraet.unc,
                                         title=self.t("geraete.dialog_" + rolle, geraet=geraet.name))
        if not ordner:
            return
        feld = self.g.source_path if rolle == "quelle" else self.g.dest_path
        feld.set(ordner.replace("/", "\\") if ordner.startswith("//") else ordner)
        self._status(self.t("geraete.gewaehlt_" + rolle, pfad=feld.get()))

    def _kopieren(self) -> None:
        geraet = self._gewaehltes()
        if geraet is None:
            return
        text = geraet.unc if geraet.art in UNC_ARTEN else geraet.adresse
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
        except tk.TclError as exc:
            logger.debug("Zwischenablage nicht beschreibbar: %s", exc)
            return
        self._status(self.t("geraete.kopiert", text=text))

    # ---- Schliessen ------------------------------------------------------------------------------------------
    def _schliessen(self) -> None:
        self._abbrechen = True
        self.win.destroy()


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int]) -> "tk.Toplevel":
    """Baut das Fenster und gibt es zurueck (das Menue oeffnet und schliesst es ueber ``_werkzeugknopf``)."""
    titel = gui._t("titlebar.geraete")
    win = gui._build_modern_toplevel(titel, 780, 520, min_width=640, min_height=400)
    gui._build_modern_header(win, titel, gui._t("geraete.untertitel"))
    win._geraete = GeraeteFenster(gui, win, schrift, pt)                 # haelt das Objekt am Leben
    return win
