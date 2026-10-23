# -*- coding: utf-8 -*-
"""Datei-Browser fuer ein PS5-PKG-Paket (seit v1.9.83).

Zeigt den inneren Baum eines ``.pkg``-Pakets via ``list-inner`` (ffpfsc-pkg-tool) in einem
:class:`ttk.Treeview` an. Ordner sind aufklappbar; einzelne Dateien oder ganze Teilbaeume
lassen sich in einen Zielordner extrahieren.

Geoeffnet vom Knopf "Dateien anzeigen" im Fenster ``Ps5PkgFenster``.

Faeden: Der Lade-Faden schreibt nur in ein :class:`queue.Queue`; ein ``after()``-Takt liest
die Ergebnisse im Tk-Faden aus.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ps5_validator.utils import ps5_pkg_werkzeug as wz

logger = logging.getLogger("PS5Converter.ui.pkg_datei_browser")

FENSTER_ATTRIBUT = "_pkg_datei_browser"
TAKT_MS = 150


def _groesse_text(n: int) -> str:
    n = max(0, int(n or 0))
    for einheit, schritt in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= schritt:
            return ("%.1f %s" % (n / schritt, einheit)).replace(".", ",")
    return "%d B" % n


def _baum_aus_eintraegen(eintraege: list[dict]) -> dict:
    """Wandelt die flache Liste von wz.baum() in einen Eltern->Kinder-Dict um.

    Jeder Schluessel ist ein vollstaendiger Pfad (mit fuehrendem ``/`` aus dem PKG).
    Der Eintrag ``""`` (leerer String) ist der virtuelle Wurzelknoten.
    """
    knoten: dict[str, dict] = {"": {"name": "/", "type": "dir", "size": 0, "kinder": []}}
    # Alle Pfade vorsortieren (Ordner zuerst, dann Dateien, je alphabetisch)
    sortiert = sorted(eintraege, key=lambda e: (e.get("type", "file") != "dir", e.get("path", "").lower()))
    fuer_elter: set[str] = set()
    for e in sortiert:
        pfad = e.get("path", "").rstrip("/")
        if not pfad:
            continue
        knoten[pfad] = {"name": pfad.rsplit("/", 1)[-1], "type": e.get("type", "file"),
                        "size": int(e.get("size") or 0), "kinder": []}
        fuer_elter.add(pfad)

    # Elternknoten sicherstellen (kann fehlen, wenn list-inner sie nicht auflistet)
    for pfad in list(fuer_elter):
        teile = pfad.split("/")
        for tiefe in range(1, len(teile)):
            elter = "/".join(teile[:tiefe])
            if elter and elter not in knoten:
                knoten[elter] = {"name": elter.rsplit("/", 1)[-1], "type": "dir", "size": 0, "kinder": []}

    # Eltern-Kind-Beziehungen aufbauen
    for pfad in knoten:
        if not pfad:
            continue
        teile = pfad.split("/")
        elter = "/".join(teile[:-1])          # fuer "/app0/eboot.bin" -> "/app0"
        if elter not in knoten:
            elter = ""
        knoten[elter]["kinder"].append(pfad)

    # Kinder alphabetisch sortieren (Ordner vor Dateien)
    for info in knoten.values():
        info["kinder"].sort(key=lambda p: (knoten[p]["type"] != "dir", knoten[p]["name"].lower()))

    return knoten


class PkgDateiBrowser:
    """Datei-Browser-Fenster fuer ein PS5-PKG-Paket."""

    def __init__(self, eltern: tk.Widget, g, werkzeug: str, paket: str, passcode: str = "") -> None:
        """
        Args:
            eltern:    Eltern-Widget fuer das Toplevel.
            g:         GUI-Objekt des Hauptprogramms (liefert ``g.t()``, ``g.c``, ``g.F``, ``g.pt``).
            werkzeug:  Pfad zum ffpfsc-pkg-tool.
            paket:     Pfad zur .pkg-Datei.
            passcode:  Passcode des Pakets (kann leer sein).
        """
        self._g = g
        self._werkzeug = werkzeug
        self._paket = paket
        self._passcode = passcode
        self._q: queue.Queue = queue.Queue()
        self._abbruch = threading.Event()
        self._knoten: dict = {}
        c = g.c
        F = g.F
        pt = g.pt

        win = tk.Toplevel(eltern)
        self.win = win
        # Besitzer setzen, sonst faellt das Fenster nach einem Klick aufs Hauptfenster dahinter.
        binden = getattr(g, "_fenster_an_hauptfenster_binden", None)
        if callable(binden):
            binden(win, eltern)
        win.title(g.t("ps5pkg.browser_title", name=os.path.basename(paket)))
        win.configure(bg=c["bg_main"])
        win.minsize(680, 460)
        win.geometry("820x560")
        win.protocol("WM_DELETE_WINDOW", self._schliessen)

        # --- Kopfzeile ---
        kopf = tk.Frame(win, bg=c["bg_main"], padx=14, pady=10)
        kopf.pack(fill="x")
        tk.Label(kopf, text=os.path.basename(paket), font=(F, pt(10), "bold"),
                 bg=c["bg_main"], fg=c["fg_primary"]).pack(side="left")

        # --- Treeview ---
        mitte = tk.Frame(win, bg=c["bg_main"])
        mitte.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        mitte.rowconfigure(0, weight=1)
        mitte.columnconfigure(0, weight=1)

        stil = ttk.Style(win)
        stil.configure("PkgBrowser.Treeview", font=(F, pt(9)), rowheight=22,
                        background=c["bg_card"], foreground=c["fg_primary"],
                        fieldbackground=c["bg_card"], borderwidth=0)
        stil.configure("PkgBrowser.Treeview.Heading", font=(F, pt(8), "bold"),
                       background=c["bg_main"], foreground=c["fg_secondary"])
        stil.map("PkgBrowser.Treeview", background=[("selected", c.get("accent", "#3a7fd5"))],
                 foreground=[("selected", "#ffffff")])

        tree = ttk.Treeview(mitte, columns=("typ", "groesse"), style="PkgBrowser.Treeview",
                             selectmode="extended", show="tree headings")
        self._tree = tree
        tree.heading("#0", text=g.t("ps5pkg.browser_col_name"), anchor="w")
        tree.heading("typ", text=g.t("ps5pkg.browser_col_type"), anchor="w")
        tree.heading("groesse", text=g.t("ps5pkg.browser_col_size"), anchor="e")
        tree.column("#0", stretch=True, minwidth=220)
        tree.column("typ", width=80, stretch=False)
        tree.column("groesse", width=100, stretch=False, anchor="e")
        tree.grid(row=0, column=0, sticky="nsew")

        ys = ttk.Scrollbar(mitte, orient="vertical", command=tree.yview)
        ys.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=ys.set)

        # --- Statuszeile ---
        status_leiste = tk.Frame(win, bg=c["bg_main"], padx=14, pady=4)
        status_leiste.pack(fill="x")
        self._status_var = tk.StringVar(value=g.t("ps5pkg.browser_loading"))
        tk.Label(status_leiste, textvariable=self._status_var, font=(F, pt(8)),
                 bg=c["bg_main"], fg=c["fg_secondary"], anchor="w").pack(side="left", fill="x", expand=True)

        # --- Knopfleiste ---
        leiste = tk.Frame(win, bg=c["bg_main"], padx=14, pady=8)
        leiste.pack(fill="x")
        self._btn_auswahl = tk.Button(leiste, text=g.t("ps5pkg.browser_btn_extract_sel"),
                                      font=(F, pt(9)), state="disabled",
                                      command=self._extrahieren_auswahl,
                                      bg=c.get("accent", "#3a7fd5"), fg="#ffffff",
                                      activebackground=c.get("accent", "#3a7fd5"),
                                      relief="flat", padx=12, pady=5)
        self._btn_auswahl.pack(side="left")
        self._btn_alle = tk.Button(leiste, text=g.t("ps5pkg.browser_btn_extract_all"),
                                   font=(F, pt(9)), state="disabled",
                                   command=self._extrahieren_alle,
                                   bg=c["bg_card"], fg=c["fg_primary"],
                                   activebackground=c["bg_card"],
                                   relief="flat", padx=12, pady=5)
        self._btn_alle.pack(side="left", padx=(8, 0))
        tk.Button(leiste, text=g.t("action.close"), font=(F, pt(9)),
                  command=self._schliessen,
                  bg=c["bg_card"], fg=c["fg_primary"],
                  activebackground=c["bg_card"],
                  relief="flat", padx=12, pady=5).pack(side="right")

        # Hintergrundfaden starten
        threading.Thread(target=self._laden_arbeit, daemon=True, name="pkg-datei-browser").start()
        win.after(TAKT_MS, self._takt)
        setattr(eltern, FENSTER_ATTRIBUT, self)

    # ------------------------------------------------------------------ Faden

    def _laden_arbeit(self) -> None:
        """Arbeitsfaden: laedt die Dateiliste; schreibt nur in die Queue."""
        try:
            eintraege = wz.baum(self._werkzeug, self._paket, passcode=self._passcode)
            self._q.put(("ok", eintraege))
        except wz.Fehler as exc:
            self._q.put(("fehler", str(exc)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("PkgDateiBrowser: Laden")
            self._q.put(("fehler", str(exc)))

    # ------------------------------------------------------------------ Takt

    def _takt(self) -> None:
        if not self.win.winfo_exists():
            return
        try:
            art, daten = self._q.get_nowait()
        except queue.Empty:
            self.win.after(TAKT_MS, self._takt)
            return
        if art == "ok":
            self._baum_einfuegen(daten)
        else:
            self._status_var.set(self._g.t("ps5pkg.browser_error", grund=daten))

    # ------------------------------------------------------------------ Baum

    def _baum_einfuegen(self, eintraege: list[dict]) -> None:
        """Fuellt den Treeview aus der flachen Eintraegsliste."""
        self._knoten = _baum_aus_eintraegen(eintraege)
        self._tree.delete(*self._tree.get_children())

        def _rekursiv(elter_pfad: str, elter_iid: str) -> None:
            info = self._knoten.get(elter_pfad, {})
            for kind_pfad in info.get("kinder", []):
                kind = self._knoten.get(kind_pfad, {})
                ist_ordner = kind.get("type") == "dir"
                zeichen = "📁" if ist_ordner else "📄"
                name = kind.get("name", kind_pfad)
                typ_text = self._g.t("ps5pkg.browser_type_dir") if ist_ordner else self._g.t("ps5pkg.browser_type_file")
                groesse = "" if ist_ordner else _groesse_text(kind.get("size", 0))
                iid = self._tree.insert(elter_iid, "end", iid=kind_pfad,
                                        text="%s  %s" % (zeichen, name),
                                        values=(typ_text, groesse))
                if ist_ordner:
                    _rekursiv(kind_pfad, iid)

        _rekursiv("", "")

        # Oberste Ebene aufklappen
        for iid in self._tree.get_children(""):
            self._tree.item(iid, open=True)

        # Zaehle Eintraege
        dateien = sum(1 for e in eintraege if e.get("type") != "dir")
        ordner = sum(1 for e in eintraege if e.get("type") == "dir")
        self._status_var.set(self._g.t("ps5pkg.browser_count", dateien=dateien, ordner=ordner))
        self._btn_auswahl.configure(state="normal")
        self._btn_alle.configure(state="normal")

    # ------------------------------------------------------------------ Extraktion

    def _alle_dateipfade(self, pfad: str) -> list[str]:
        """Alle Dateipfade (keine Ordner) unterhalb von ``pfad`` (inklusive ``pfad`` selbst, wenn Datei)."""
        info = self._knoten.get(pfad)
        if info is None:
            return []
        if info.get("type") != "dir":
            return [pfad]
        erg: list[str] = []
        for kind in info.get("kinder", []):
            erg.extend(self._alle_dateipfade(kind))
        return erg

    def _ziel_waehlen(self) -> str | None:
        ziel = filedialog.askdirectory(parent=self.win, title=self._g.t("ps5pkg.browser_choose_target"))
        return ziel if ziel else None

    def _extrahieren_auswahl(self) -> None:
        auswahl = list(self._tree.selection())
        if not auswahl:
            messagebox.showinfo(self._g.t("ps5pkg.browser_title_short"),
                                self._g.t("ps5pkg.browser_no_selection"), parent=self.win)
            return
        pfade: list[str] = []
        for iid in auswahl:
            pfade.extend(self._alle_dateipfade(iid))
        pfade = list(dict.fromkeys(pfade))         # Duplikate entfernen, Reihenfolge erhalten
        if not pfade:
            return
        ziel = self._ziel_waehlen()
        if not ziel:
            return
        self._extrahieren_starten(pfade, ziel)

    def _extrahieren_alle(self) -> None:
        ziel = self._ziel_waehlen()
        if not ziel:
            return
        alle = self._alle_dateipfade("")
        if not alle:
            return
        self._extrahieren_starten(alle, ziel)

    def _extrahieren_starten(self, pfade: list[str], ziel: str) -> None:
        self._btn_auswahl.configure(state="disabled")
        self._btn_alle.configure(state="disabled")
        self._status_var.set(self._g.t("ps5pkg.browser_extracting", anzahl=len(pfade)))
        threading.Thread(target=self._extrahieren_arbeit, args=(pfade, ziel),
                         daemon=True, name="pkg-browser-extract").start()
        self.win.after(TAKT_MS, self._takt_extraktion)

    def _extrahieren_arbeit(self, pfade: list[str], ziel: str) -> None:
        try:
            wz.mitglieder_extrahieren(self._werkzeug, self._paket, ziel, pfade, passcode=self._passcode,
                                      arbeitsordner=self._g._arbeitsordner())
            self._q.put(("extract_ok", ziel))
        except wz.Fehler as exc:
            self._q.put(("extract_fehler", str(exc)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("PkgDateiBrowser: Extrahieren")
            self._q.put(("extract_fehler", str(exc)))

    def _takt_extraktion(self) -> None:
        if not self.win.winfo_exists():
            return
        try:
            art, daten = self._q.get_nowait()
        except queue.Empty:
            self.win.after(TAKT_MS, self._takt_extraktion)
            return
        self._btn_auswahl.configure(state="normal")
        self._btn_alle.configure(state="normal")
        if art == "extract_ok":
            self._status_var.set(self._g.t("ps5pkg.browser_extracted_ok", ordner=daten))
        else:
            self._status_var.set(self._g.t("ps5pkg.browser_extracted_fehler", grund=daten))
            messagebox.showerror(self._g.t("ps5pkg.browser_title_short"),
                                 self._g.t("ps5pkg.browser_extracted_fehler", grund=daten), parent=self.win)

    # ------------------------------------------------------------------ Schliessen

    def _schliessen(self) -> None:
        self._abbruch.set()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
