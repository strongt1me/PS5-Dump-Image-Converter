# -*- coding: utf-8 -*-
"""Spiel-Detail-Fenster fuer PS5-Spielordner (seit v1.9.83).

Zeigt drei Registerkarten:
- SELF/ELF: alle signierten Ausfuehrdateien im Spielordner mit Auth-Kategorie und Typ.
- Aktivitaeten: Eintraege aus sce_sys/activity.json als Tabelle.
- Trophaaen: Trophaaen-Sets aus sce_sys/trophy/ oder sce_trophy/.

Geoeffnet vom Knopf "Details" im Fenster ``Ps5PkgFenster`` (nur fuer Spielordner).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from ps5_validator.utils import self_reader as sr

logger = logging.getLogger("PS5Converter.ui.spiel_detail_fenster")

FENSTER_ATTRIBUT = "_spiel_detail_fenster"
TAKT_MS = 150
_SELF_ORDNER = ("app0", "sce_module", "sce_sys")
_SELF_ENDUNGEN = (".bin", ".prx", ".elf", ".self", ".sprx", ".fself")


def _groesse_text(n: int) -> str:
    n = max(0, int(n or 0))
    for einheit, schritt in (("MB", 1024 ** 2), ("KB", 1024)):
        if n >= schritt:
            return ("%.1f %s" % (n / schritt, einheit)).replace(".", ",")
    return "%d B" % n


def _self_dateien_suchen(spielordner: str) -> list[str]:
    """Alle moeglichen SELF/ELF-Dateien im Spielordner (rekursiv bis Tiefe 4)."""
    gefunden: list[str] = []
    for wurzel in _SELF_ORDNER:
        basis = os.path.join(spielordner, wurzel)
        if not os.path.isdir(basis):
            continue
        for dp, _dirs, dateien in os.walk(basis):
            tiefe = dp.replace(spielordner, "").count(os.sep)
            if tiefe > 5:
                break
            for name in sorted(dateien):
                _, ext = os.path.splitext(name.lower())
                if ext in _SELF_ENDUNGEN:
                    gefunden.append(os.path.join(dp, name))
    return gefunden


def _activity_lesen(spielordner: str) -> list[dict]:
    """Eintraege aus sce_sys/activity.json; leere Liste wenn nicht vorhanden."""
    pfad = os.path.join(spielordner, "sce_sys", "activity.json")
    if not os.path.isfile(pfad):
        return []
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            daten = json.load(f)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(daten, list):
        return [e for e in daten if isinstance(e, dict)]
    if isinstance(daten, dict):
        werte = daten.get("activities") or daten.get("activity") or []
        if isinstance(werte, list):
            return [e for e in werte if isinstance(e, dict)]
        return [daten]
    return []


def _trophy_sets_suchen(spielordner: str) -> list[str]:
    """TRP-Dateipfade unter sce_sys/trophy/ oder sce_trophy/."""
    ergebnis: list[str] = []
    for suchpfad in (os.path.join(spielordner, "sce_sys", "trophy"),
                     os.path.join(spielordner, "sce_trophy")):
        if not os.path.isdir(suchpfad):
            continue
        for dp, _dirs, dateien in os.walk(suchpfad):
            for name in sorted(dateien):
                if name.lower().endswith(".trp"):
                    ergebnis.append(os.path.join(dp, name))
    return ergebnis


class SpielDetailFenster:
    """Detail-Fenster mit SELF-, Aktivitaets- und Trophaaen-Registerkarten."""

    def __init__(self, eltern: tk.Widget, g, spielordner: str, titel: str = "") -> None:
        self._g = g
        self._spielordner = spielordner
        self._q: queue.Queue = queue.Queue()
        self._abbruch = threading.Event()
        c = g.c
        F = g.F
        pt = g.pt
        t = g.t

        win = tk.Toplevel(eltern)
        self.win = win
        fenstertitel = titel or os.path.basename(spielordner)
        win.title(t("ps5pkg.detail_title", name=fenstertitel))
        win.configure(bg=c["bg_main"])
        win.minsize(700, 480)
        win.geometry("860x580")
        win.protocol("WM_DELETE_WINDOW", self._schliessen)

        # --- Kopfzeile ---
        kopf = tk.Frame(win, bg=c["bg_main"], padx=14, pady=8)
        kopf.pack(fill="x")
        tk.Label(kopf, text=fenstertitel, font=(F, pt(10), "bold"),
                 bg=c["bg_main"], fg=c["fg_primary"]).pack(side="left")

        # --- Notebook ---
        stil = ttk.Style(win)
        stil.configure("Detail.TNotebook", background=c["bg_main"], borderwidth=0)
        stil.configure("Detail.TNotebook.Tab", font=(F, pt(9)), padding=(12, 5))
        nb = ttk.Notebook(win, style="Detail.TNotebook")
        nb.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self._seite_self = tk.Frame(nb, bg=c["bg_main"])
        self._seite_akt = tk.Frame(nb, bg=c["bg_main"])
        self._seite_trophy = tk.Frame(nb, bg=c["bg_main"])
        nb.add(self._seite_self, text=t("ps5pkg.detail_tab_self"))
        nb.add(self._seite_akt, text=t("ps5pkg.detail_tab_activity"))
        nb.add(self._seite_trophy, text=t("ps5pkg.detail_tab_trophy"))

        self._baue_self_seite(c, F, pt)
        self._baue_akt_seite(c, F, pt)
        self._baue_trophy_seite(c, F, pt)

        # --- Knopfleiste ---
        leiste = tk.Frame(win, bg=c["bg_main"], padx=14, pady=6)
        leiste.pack(fill="x")
        tk.Button(leiste, text=t("action.close"), font=(F, pt(9)),
                  command=self._schliessen,
                  bg=c["bg_card"], fg=c["fg_primary"],
                  activebackground=c["bg_card"],
                  relief="flat", padx=12, pady=5).pack(side="right")

        self._lade_faden = threading.Thread(target=self._laden_arbeit, daemon=True, name="spiel-detail")
        self._lade_faden.start()
        win.after(TAKT_MS, self._takt)

    # ------------------------------------------------------------------
    # Seiten-Aufbau
    # ------------------------------------------------------------------

    def _baue_self_seite(self, c, F, pt) -> None:
        seite = self._seite_self
        seite.rowconfigure(0, weight=1)
        seite.columnconfigure(0, weight=1)
        stil = ttk.Style(seite)
        stil.configure("SelfTree.Treeview", font=(F, pt(9)), rowheight=20,
                        background=c["bg_card"], foreground=c["fg_primary"],
                        fieldbackground=c["bg_card"], borderwidth=0)
        stil.configure("SelfTree.Treeview.Heading", font=(F, pt(8), "bold"),
                       background=c["bg_main"], foreground=c["fg_secondary"])
        self._self_tree = ttk.Treeview(seite, columns=("typ", "auth", "groesse"),
                                        style="SelfTree.Treeview", show="tree headings")
        t = self._g.t
        self._self_tree.heading("#0", text=t("ps5pkg.detail_col_file"), anchor="w")
        self._self_tree.heading("typ", text=t("ps5pkg.detail_col_type"), anchor="w")
        self._self_tree.heading("auth", text=t("ps5pkg.detail_col_auth"), anchor="w")
        self._self_tree.heading("groesse", text=t("ps5pkg.detail_col_size"), anchor="e")
        self._self_tree.column("#0", stretch=True, minwidth=200)
        self._self_tree.column("typ", width=120, stretch=False)
        self._self_tree.column("auth", width=150, stretch=False)
        self._self_tree.column("groesse", width=90, stretch=False, anchor="e")
        self._self_tree.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(seite, orient="vertical", command=self._self_tree.yview)
        ys.grid(row=0, column=1, sticky="ns")
        self._self_tree.configure(yscrollcommand=ys.set)
        self._self_status = tk.Label(seite, text=t("ps5pkg.detail_loading"),
                                      font=(F, pt(8)), bg=c["bg_main"], fg=c["fg_secondary"], anchor="w")
        self._self_status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(4, 0))

    def _baue_akt_seite(self, c, F, pt) -> None:
        seite = self._seite_akt
        seite.rowconfigure(0, weight=1)
        seite.columnconfigure(0, weight=1)
        stil = ttk.Style(seite)
        stil.configure("AktTree.Treeview", font=(F, pt(9)), rowheight=20,
                        background=c["bg_card"], foreground=c["fg_primary"],
                        fieldbackground=c["bg_card"], borderwidth=0)
        stil.configure("AktTree.Treeview.Heading", font=(F, pt(8), "bold"),
                       background=c["bg_main"], foreground=c["fg_secondary"])
        self._akt_tree = ttk.Treeview(seite, columns=("typ", "wert"),
                                       style="AktTree.Treeview", show="tree headings")
        t = self._g.t
        self._akt_tree.heading("#0", text=t("ps5pkg.detail_col_name"), anchor="w")
        self._akt_tree.heading("typ", text=t("ps5pkg.detail_col_type"), anchor="w")
        self._akt_tree.heading("wert", text=t("ps5pkg.detail_col_value"), anchor="w")
        self._akt_tree.column("#0", stretch=True, minwidth=160)
        self._akt_tree.column("typ", width=100, stretch=False)
        self._akt_tree.column("wert", width=200, stretch=True)
        self._akt_tree.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(seite, orient="vertical", command=self._akt_tree.yview)
        ys.grid(row=0, column=1, sticky="ns")
        self._akt_tree.configure(yscrollcommand=ys.set)
        self._akt_status = tk.Label(seite, text=t("ps5pkg.detail_loading"),
                                     font=(F, pt(8)), bg=c["bg_main"], fg=c["fg_secondary"], anchor="w")
        self._akt_status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(4, 0))

    def _baue_trophy_seite(self, c, F, pt) -> None:
        seite = self._seite_trophy
        seite.rowconfigure(0, weight=1)
        seite.columnconfigure(0, weight=1)
        stil = ttk.Style(seite)
        stil.configure("TrpTree.Treeview", font=(F, pt(9)), rowheight=20,
                        background=c["bg_card"], foreground=c["fg_primary"],
                        fieldbackground=c["bg_card"], borderwidth=0)
        stil.configure("TrpTree.Treeview.Heading", font=(F, pt(8), "bold"),
                       background=c["bg_main"], foreground=c["fg_secondary"])
        self._trp_tree = ttk.Treeview(seite, columns=("groesse",),
                                       style="TrpTree.Treeview", show="tree headings")
        t = self._g.t
        self._trp_tree.heading("#0", text=t("ps5pkg.detail_col_file"), anchor="w")
        self._trp_tree.heading("groesse", text=t("ps5pkg.detail_col_size"), anchor="e")
        self._trp_tree.column("#0", stretch=True, minwidth=240)
        self._trp_tree.column("groesse", width=100, stretch=False, anchor="e")
        self._trp_tree.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(seite, orient="vertical", command=self._trp_tree.yview)
        ys.grid(row=0, column=1, sticky="ns")
        self._trp_tree.configure(yscrollcommand=ys.set)
        self._trp_status = tk.Label(seite, text=t("ps5pkg.detail_loading"),
                                     font=(F, pt(8)), bg=c["bg_main"], fg=c["fg_secondary"], anchor="w")
        self._trp_status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(4, 0))

    # ------------------------------------------------------------------
    # Hintergrundfaden
    # ------------------------------------------------------------------

    def _laden_arbeit(self) -> None:
        t = self._g.t
        ordner = self._spielordner

        # SELF/ELF
        self_infos: list[tuple[str, str, str, int]] = []
        try:
            for pfad in _self_dateien_suchen(ordner):
                if self._abbruch.is_set():
                    break
                rel = os.path.relpath(pfad, ordner)
                groesse = 0
                try:
                    groesse = os.path.getsize(pfad)
                except OSError:
                    pass
                typ_text = ""
                auth_text = ""
                try:
                    info = sr.read_self(pfad)
                    typ_text = info.magic_name
                    if info.ext_info:
                        auth_text = info.ext_info.authority_category_name
                    elif info.container == sr.CONTAINER_ELF:
                        auth_text = "–"
                except sr.SelfParseError:
                    typ_text = t("ps5pkg.detail_not_self")
                except Exception as exc:  # noqa: BLE001
                    typ_text = "?"
                    logger.debug("SELF lesen %s: %s", rel, exc)
                self_infos.append((rel, typ_text, auth_text, groesse))
        except Exception as exc:  # noqa: BLE001
            logger.debug("SELF-Suche: %s", exc)
        self._q.put(("self", self_infos))

        # Aktivitaeten
        akt_eintraege = _activity_lesen(ordner)
        self._q.put(("akt", akt_eintraege))

        # Trophaaen
        trp_dateien: list[tuple[str, int]] = []
        try:
            for pfad in _trophy_sets_suchen(ordner):
                rel = os.path.relpath(pfad, ordner)
                groesse = 0
                try:
                    groesse = os.path.getsize(pfad)
                except OSError:
                    pass
                trp_dateien.append((rel, groesse))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Trophy-Suche: %s", exc)
        self._q.put(("trp", trp_dateien))

        self._q.put(("fertig", None))

    def _takt(self) -> None:
        try:
            while True:
                art, daten = self._q.get_nowait()
                if art == "self":
                    self._self_fuellen(daten)
                elif art == "akt":
                    self._akt_fuellen(daten)
                elif art == "trp":
                    self._trp_fuellen(daten)
                elif art == "fertig":
                    return
        except queue.Empty:
            pass
        try:
            self.win.after(TAKT_MS, self._takt)
        except tk.TclError:
            pass

    def _self_fuellen(self, infos: list[tuple[str, str, str, int]]) -> None:
        t = self._g.t
        for rel, typ, auth, groesse in infos:
            self._self_tree.insert("", "end", text=rel,
                                   values=(typ, auth, _groesse_text(groesse)))
        n = len(infos)
        self._self_status.configure(text=t("ps5pkg.detail_self_count", n=n) if n else t("ps5pkg.detail_self_none"))

    def _akt_fuellen(self, eintraege: list[dict]) -> None:
        t = self._g.t
        for eintrag in eintraege:
            name = str(eintrag.get("activityId") or eintrag.get("name") or "–")
            typ = str(eintrag.get("type") or "–")
            wert = str(eintrag.get("targetCount") or eintrag.get("requirement") or "–")
            self._akt_tree.insert("", "end", text=name, values=(typ, wert))
        n = len(eintraege)
        self._akt_status.configure(text=t("ps5pkg.detail_akt_count", n=n) if n else t("ps5pkg.detail_akt_none"))

    def _trp_fuellen(self, dateien: list[tuple[str, int]]) -> None:
        t = self._g.t
        for rel, groesse in dateien:
            self._trp_tree.insert("", "end", text=rel, values=(_groesse_text(groesse),))
        n = len(dateien)
        self._trp_status.configure(text=t("ps5pkg.detail_trp_count", n=n) if n else t("ps5pkg.detail_trp_none"))

    def _schliessen(self) -> None:
        self._abbruch.set()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
