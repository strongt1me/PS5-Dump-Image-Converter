# -*- coding: utf-8 -*-
"""Der Dialog "Optionen" des Fensters "PS5 PKG Dump & Image Converter" (Nutzerwunsch 11.10.2026).

Vier Register: **Bibliothek** (Ordner, Unterordner, Aktualisieren beim Start, Quellen entfernen), **Darstellung** (Cover,
Sortierung), **Ausgabe & Vorgaben** (Zielordner, Temp-Ordner, Aktion, Zielformat, Standard-Builder, Debug-Passcode,
Ausgabeordner oeffnen) und **Wartung** (Export, Import, Zuruecksetzen). Nichts wird vor "Speichern" uebernommen;
"Abbrechen" und das X lassen alles, wie es war.

**Standard-Builder** (seit 12.10.2026, wie in der Vorlage - der eigenen PKG-App des Nutzers): welches Werkzeug "Paket
bauen" verwendet, LibProsperoPkg 1.2.0 (``ffpfsc-pkg-tool``, Vorgabe) oder ProsperoPkgTool (zweiter, MIT-lizenzierter
Paketersteller, :mod:`ps5_validator.utils.prospero_pkg_tool`). Gilt nur fuer den Bau - Lesen, Pruefen und Entpacken
bleiben immer bei ``ffpfsc-pkg-tool``, das als einziges Passcode, CNT-Metadaten und JSON-Ausgabe kennt.

**Temp-Ordner** (seit v1.9.83): eigener Arbeitsordner fuer Entpacken/Bauen/Extrahieren dieses Fensters, nur bei
Bedarf gesetzt (leer = Vorgabe wie bisher, siehe ``Ps5PkgFenster._arbeitsordner``).

Die Bausteine kommen aus dem Fenster-Kit (``g._pw``): nichts davon bleibt nach dem Schliessen im Hauptprogramm stehen
(``test_fenster_leck``). Die Regeln - was ein Wert sein darf, was ein Import aendert - stehen in
:mod:`ps5_validator.utils.ps5_pkg_optionen`.
"""
from __future__ import annotations

import json
import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox

from ps5_validator.utils import ps5_pkg_optionen as opt

logger = logging.getLogger("PS5Converter.ui.ps5_pkg_optionen")


def _int_safe(wert: str, vorgabe: int) -> int:
    try:
        return int(str(wert).strip())
    except (ValueError, TypeError):
        return vorgabe


#: Name des Dialogs am Fenster (ein zweiter Aufruf holt den offenen nach vorn).
DIALOG_ATTRIBUT = "_optionen_dialog"
#: (Schluessel, i18n-Schluessel des Registers) in der Reihenfolge der Register.
REGISTER = (("bibliothek", "ps5pkg.opt_tab_library"), ("darstellung", "ps5pkg.opt_tab_view"),
            ("ausgabe", "ps5pkg.opt_tab_output"), ("bau", "ps5pkg.opt_tab_build"),
            ("wartung", "ps5pkg.opt_tab_maint"))
EXPORT_NAME = "PS5PKGTool-Optionen.json"


def oeffnen(fenster) -> "Optionen":
    """Oeffnet den Dialog - oder holt den offenen nach vorn."""
    vorhanden = getattr(fenster, DIALOG_ATTRIBUT, None)
    if vorhanden is not None:
        try:
            if vorhanden.win.winfo_exists():
                vorhanden.win.deiconify()
                vorhanden.win.lift()
                return vorhanden
        except tk.TclError:
            pass
    dialog = Optionen(fenster)
    setattr(fenster, DIALOG_ATTRIBUT, dialog)
    return dialog


class Optionen:
    def __init__(self, fenster) -> None:
        self.f = fenster
        g = fenster.g
        self.c, self.F, self.M, self.pt, self.t = fenster.c, fenster.F, fenster.M, fenster.pt, fenster.t
        self.pw = g._pw
        self.aktuell = opt.lesen(fenster._einstellung)
        self.ordner: list[str] = list(self.aktuell[opt.ORDNER])
        self.quellen: list[str] = [i.pfad for i in fenster.pakete]
        self.entfernt: list[str] = []                 # Quellen, die beim Speichern aus der Bibliothek verschwinden
        self.neue_quellen: list[str] = []             # aus einem Import: kommen beim Speichern dazu
        self._register_rahmen: dict[str, tk.Frame] = {}
        self._register_tabs: dict[str, tuple[tk.Label, tk.Frame]] = {}

        self.win = g._build_modern_toplevel(fenster.t("ps5pkg.opt_window_title"), 960, 660, min_width=840, min_height=580)
        self.win.configure(bg=self.c["bg_main"])
        try:
            self.win.transient(fenster.win.winfo_toplevel())
        except tk.TclError:
            pass
        self.rekursiv_var = tk.BooleanVar(master=self.win)
        self.start_var = tk.BooleanVar(master=self.win)
        self.cover_var = tk.BooleanVar(master=self.win)
        self.oeffnen_var = tk.BooleanVar(master=self.win)
        self.ziel_var = tk.StringVar(master=self.win)
        self.temp_ordner_var = tk.StringVar(master=self.win)
        self.sort_var = tk.StringVar(master=self.win)
        self.aktion_var = tk.StringVar(master=self.win)
        self.format_var = tk.StringVar(master=self.win)
        self.passcode_var = tk.StringVar(master=self.win)
        self.passcode_zeigen_var = tk.BooleanVar(master=self.win)
        self.builder_var = tk.StringVar(master=self.win)
        self.kraken_modus_var = tk.StringVar(master=self.win)
        self.kraken_stufe_var = tk.StringVar(master=self.win)
        self.kraken_kerne_var = tk.StringVar(master=self.win)
        self.playgo_chunks_var = tk.StringVar(master=self.win)
        self.deterministisch_var = tk.BooleanVar(master=self.win)
        self.regen_playgo_var = tk.BooleanVar(master=self.win)
        self.backport_einbauen_var = tk.BooleanVar(master=self.win)
        self.backport_firmware_var = tk.StringVar(master=self.win)
        self.backport_fakelib_var = tk.StringVar(master=self.win)
        self.min_fw_var = tk.StringVar(master=self.win)
        self.patch_modus_var = tk.BooleanVar(master=self.win)
        self._bauen()
        self._felder_fuellen(self.aktuell)
        self._liste_zeigen()
        self.zeigen("bibliothek")
        self.win.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.win.bind("<Escape>", lambda _e: self.schliessen())

    # ------------------------------------------------------------------
    # Namen der Auswahlen (sprachabhaengig, gespeichert wird der Schluessel)
    # ------------------------------------------------------------------
    def _sortierungen(self) -> dict[str, str]:
        return {"titel": self.t("ps5pkg.opt_sort_title"), "titel_id": self.t("ps5pkg.opt_sort_id"),
                "groesse": self.t("ps5pkg.opt_sort_size")}

    def _aktionen(self) -> dict[str, str]:
        return {"umwandeln": self.t("ps5pkg.action_convert"), "extrahieren": self.t("ps5pkg.action_extract"),
                "pruefen": self.t("ps5pkg.action_check")}

    def _formate(self) -> dict[str, str]:
        return {"ffpkg": "FFPKG (.ffpkg)", "ffpfsc": "FFPFSC (.ffpfsc)", "ffpfs": "FFPFS (.ffpfs)",
                "exfat": "exFAT (.exfat)"}

    def _builder(self) -> dict[str, str]:
        return {"lpp": "LibProsperoPkg 1.2.0", "ppt": "ProsperoPkgTool"}

    @staticmethod
    def _schluessel_zu(namen: dict[str, str], text: str, vorgabe: str) -> str:
        return next((k for k, v in namen.items() if v == text), vorgabe)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _bauen(self) -> None:
        c, F, pt, t = self.c, self.F, self.pt, self.t
        kopf = tk.Frame(self.win, bg=c["bg_main"])
        kopf.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(kopf, text=t("ps5pkg.nav_options"), font=(F, pt(18), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"]).pack(anchor="w")
        leiste = tk.Frame(self.win, bg=c["bg_main"])
        leiste.pack(fill="x", padx=18, pady=(10, 0))
        for schluessel, text in REGISTER:
            tab = tk.Frame(leiste, bg=c["bg_main"], cursor="hand2")
            tab.pack(side="left", padx=(0, 18))
            name = tk.Label(tab, text=t(text), font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_secondary"], cursor="hand2")
            name.pack()
            strich = tk.Frame(tab, height=2, bg=c["bg_main"])
            strich.pack(fill="x", pady=(4, 0))
            for w in (tab, name):
                w.bind("<Button-1>", lambda _e, s=schluessel: self.zeigen(s))
            self._register_tabs[schluessel] = (name, strich)
        tk.Frame(self.win, height=1, bg=c["border"]).pack(fill="x", padx=18)

        fuss = tk.Frame(self.win, bg=c["bg_main"])
        fuss.pack(side="bottom", fill="x", padx=18, pady=14)
        self.pw.Button(fuss, text=t("ps5pkg.opt_cancel"), command=self.schliessen).pack(side="right")
        self.pw.Button(fuss, text=t("ps5pkg.opt_save"), command=self.speichern, style="Accent.TButton").pack(
            side="right", padx=(0, 10))

        inhalt = tk.Frame(self.win, bg=c["bg_main"])
        inhalt.pack(fill="both", expand=True, padx=18, pady=(12, 0))
        inhalt.columnconfigure(0, weight=1)
        inhalt.rowconfigure(0, weight=1)
        _KARTE_SCHLUESSEL = {"bibliothek": "library", "darstellung": "view",
                             "ausgabe": "output", "bau": "build", "wartung": "maint"}
        for schluessel, _text in REGISTER:
            rahmen = self.f._karte(inhalt, "ps5pkg.opt_tab_" + _KARTE_SCHLUESSEL[schluessel])
            rahmen.grid(row=0, column=0, sticky="nsew")
            self._register_rahmen[schluessel] = rahmen
        self._register_bibliothek(self._register_rahmen["bibliothek"])
        self._register_darstellung(self._register_rahmen["darstellung"])
        self._register_ausgabe(self._register_rahmen["ausgabe"])
        self._register_bau(self._register_rahmen["bau"])
        self._register_wartung(self._register_rahmen["wartung"])

    def zeigen(self, schluessel: str) -> None:
        c = self.c
        self._register_rahmen[schluessel].tkraise()
        for name, (text, strich) in self._register_tabs.items():
            aktiv = name == schluessel
            text.configure(fg=c["fg_accent"] if aktiv else c["fg_secondary"])
            strich.configure(bg=c["fg_accent"] if aktiv else c["bg_main"])

    def _info(self, eltern, schluessel: str) -> None:
        tk.Label(eltern, text=self.t(schluessel), font=(self.F, self.pt(10)), bg=self.c["bg_card"],
                 fg=self.c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(0, 10))

    def _beschriftung(self, eltern, schluessel: str) -> tk.Label:
        return tk.Label(eltern, text=self.t(schluessel), font=(self.F, self.pt(10)), bg=self.c["bg_card"],
                        fg=self.c["fg_primary"], anchor="w")

    def _haken(self, eltern, schluessel: str, variable) -> None:
        self.pw.Checkbutton(eltern, text=self.t(schluessel), variable=variable, font=(self.F, self.pt(10))).pack(
            anchor="w", pady=(4, 0))

    # --- Bibliothek ---------------------------------------------------
    def _register_bibliothek(self, karte) -> None:
        c, F, pt = self.c, self.F, self.pt
        self._info(karte, "ps5pkg.opt_lib_info")
        spalten = tk.Frame(karte, bg=c["bg_card"])
        spalten.pack(fill="both", expand=True)
        for i in (0, 1):
            spalten.columnconfigure(i, weight=1, uniform="opt")
        spalten.rowconfigure(1, weight=1)
        self._beschriftung(spalten, "ps5pkg.opt_lib_folders").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._beschriftung(spalten, "ps5pkg.opt_lib_sources").grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 4))
        self.ordner_liste = self.pw.Listbox(spalten, height=8, exportselection=False, font=(F, pt(10)))
        self.ordner_liste.grid(row=1, column=0, sticky="nsew")
        self.quellen_liste = self.pw.Listbox(spalten, height=8, exportselection=False, font=(F, pt(10)),
                                             selectmode="extended")
        self.quellen_liste.grid(row=1, column=1, sticky="nsew", padx=(12, 0))
        knoepfe_links = tk.Frame(spalten, bg=c["bg_card"])
        knoepfe_links.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.pw.Button(knoepfe_links, text=self.t("ps5pkg.opt_add_folder"), command=self._ordner_hinzu).pack(side="left")
        self.pw.Button(knoepfe_links, text=self.t("ps5pkg.opt_remove_folder"), command=self._ordner_weg).pack(
            side="left", padx=(8, 0))
        knoepfe_rechts = tk.Frame(spalten, bg=c["bg_card"])
        knoepfe_rechts.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(8, 0))
        self.pw.Button(knoepfe_rechts, text=self.t("ps5pkg.opt_remove_source"), command=self._quelle_weg).pack(side="left")
        self._haken(karte, "ps5pkg.opt_recursive", self.rekursiv_var)
        self._haken(karte, "ps5pkg.opt_start_scan", self.start_var)
        tk.Label(karte, text=self.t("ps5pkg.opt_lib_note"), font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"],
                 anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(10, 0))

    def _liste_zeigen(self) -> None:
        self.ordner_liste.delete(0, "end")
        for p in self.ordner:
            self.ordner_liste.insert("end", p)
        self.quellen_liste.delete(0, "end")
        for p in self.quellen + self.neue_quellen:
            if p not in self.entfernt:
                self.quellen_liste.insert("end", p)

    def _ordner_hinzu(self) -> None:
        gewaehlt = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.opt_add_folder"))
        if gewaehlt:
            gewaehlt = os.path.normpath(gewaehlt)
            if gewaehlt not in self.ordner:
                self.ordner.append(gewaehlt)
                self._liste_zeigen()

    def _ordner_weg(self) -> None:
        for index in reversed(self.ordner_liste.curselection()):
            del self.ordner[int(index)]
        self._liste_zeigen()

    def _quelle_weg(self) -> None:
        sichtbar = [p for p in self.quellen + self.neue_quellen if p not in self.entfernt]
        for index in self.quellen_liste.curselection():
            pfad = sichtbar[int(index)]
            if pfad in self.neue_quellen:
                self.neue_quellen.remove(pfad)
            else:
                self.entfernt.append(pfad)
        self._liste_zeigen()

    def _kraken_modi(self) -> dict[str, str]:
        return {"kraken": "Kraken", "zlib": "Zlib", "none": self.t("ps5pkg.opt_build_mode_none")}

    # --- Bau-Einstellungen ----------------------------------------------
    def _register_bau(self, karte) -> None:
        c, F, pt, t = self.c, self.F, self.pt, self.t
        self._info(karte, "ps5pkg.opt_build_info")

        # Kompressionsmodus
        self._beschriftung(karte, "ps5pkg.opt_build_mode").pack(anchor="w")
        self.kraken_modus_box = self.pw.Combobox(karte, textvariable=self.kraken_modus_var,
                                                 values=list(self._kraken_modi().values()),
                                                 state="readonly", width=18)
        self.kraken_modus_box.pack(anchor="w", pady=(4, 10))

        # Kompressionsstufe + Threads nebeneinander
        zeile = tk.Frame(karte, bg=c["bg_card"])
        zeile.pack(fill="x", pady=(0, 10))
        tk.Label(zeile, text=t("ps5pkg.opt_build_level"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=0, column=0, sticky="w")
        self.pw.Spinbox(zeile, textvariable=self.kraken_stufe_var, from_=-4, to=9, width=6,
                        font=(F, pt(10))).grid(row=0, column=1, padx=(8, 24))
        tk.Label(zeile, text=t("ps5pkg.opt_build_cores"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=0, column=2, sticky="w")
        self.pw.Spinbox(zeile, textvariable=self.kraken_kerne_var, from_=0, to=256, width=6,
                        font=(F, pt(10))).grid(row=0, column=3, padx=(8, 0))
        tk.Label(karte, text=t("ps5pkg.opt_build_cores_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w").pack(fill="x", pady=(0, 10))

        # PlayGo-Chunks
        zeile2 = tk.Frame(karte, bg=c["bg_card"])
        zeile2.pack(fill="x", pady=(0, 10))
        tk.Label(zeile2, text=t("ps5pkg.opt_build_playgo"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").pack(side="left")
        self.pw.Spinbox(zeile2, textvariable=self.playgo_chunks_var, from_=1, to=255, width=6,
                        font=(F, pt(10))).pack(side="left", padx=(8, 0))
        tk.Label(karte, text=t("ps5pkg.opt_build_playgo_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w").pack(fill="x", pady=(0, 10))

        # Deterministisch
        self._haken(karte, "ps5pkg.opt_build_deterministic", self.deterministisch_var)
        tk.Label(karte, text=t("ps5pkg.opt_build_deterministic_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 10))

        # PlayGo neu generieren
        self._haken(karte, "ps5pkg.opt_build_regen_playgo", self.regen_playgo_var)
        tk.Label(karte, text=t("ps5pkg.opt_build_regen_playgo_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 10))

        # Backport einbauen
        self._haken(karte, "ps5pkg.opt_build_backport", self.backport_einbauen_var)
        tk.Label(karte, text=t("ps5pkg.opt_build_backport_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 4))
        bp_zeile = tk.Frame(karte, bg=c["bg_card"])
        bp_zeile.pack(anchor="w", pady=(0, 4))
        tk.Label(bp_zeile, text=t("ps5pkg.opt_build_backport_fw"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"]).pack(side="left", padx=(0, 8))
        from ps5_validator.utils import ps5_pkg_backport as bp_util
        fw_werte = [str(fw) for fw in bp_util.firmwares_fuer_auswahl("")]
        self.backport_fw_combo = self.pw.Combobox(bp_zeile, textvariable=self.backport_firmware_var,
                                                  values=fw_werte, state="readonly", width=8)
        self.backport_fw_combo.pack(side="left")
        tk.Label(bp_zeile, text=t("ps5pkg.opt_build_backport_fw_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"]).pack(side="left", padx=(8, 0))
        self._beschriftung(karte, "ps5pkg.opt_build_backport_fakelib").pack(anchor="w", pady=(8, 0))
        fakelib_zeile = tk.Frame(karte, bg=c["bg_card"])
        fakelib_zeile.pack(fill="x", pady=(4, 0))
        fakelib_zeile.columnconfigure(0, weight=1)
        self.pw.Entry(fakelib_zeile, textvariable=self.backport_fakelib_var, font=(F, pt(10)),
                      bg=c["bg_main"], fg=c["fg_primary"], insertbackground=c["fg_primary"],
                      relief="flat").grid(row=0, column=0, sticky="ew", ipady=3)
        self.pw.Button(fakelib_zeile, text=self.t("ps5pkg.opt_build_backport_fakelib_choose"),
                       command=self._fakelib_waehlen).grid(row=0, column=1, padx=(8, 0))
        tk.Label(karte, text=t("ps5pkg.opt_build_backport_fakelib_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 0))

        self._beschriftung(karte, "ps5pkg.opt_build_min_fw").pack(anchor="w", pady=(14, 4))
        self.pw.Entry(karte, textvariable=self.min_fw_var, font=(F, pt(10)), width=10,
                      bg=c["bg_main"], fg=c["fg_primary"], insertbackground=c["fg_primary"],
                      relief="flat").pack(anchor="w", ipady=3)
        tk.Label(karte, text=t("ps5pkg.opt_build_min_fw_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 12))
        self._haken(karte, "ps5pkg.opt_build_patch_modus", self.patch_modus_var)
        tk.Label(karte, text=t("ps5pkg.opt_build_patch_modus_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 0))

    # --- Darstellung ----------------------------------------------------
    def _register_darstellung(self, karte) -> None:
        self._info(karte, "ps5pkg.opt_view_info")
        self._haken(karte, "ps5pkg.opt_cover", self.cover_var)
        self._beschriftung(karte, "ps5pkg.opt_sort").pack(anchor="w", pady=(14, 4))
        self.sort_box = self.pw.Combobox(karte, textvariable=self.sort_var, values=list(self._sortierungen().values()),
                                         state="readonly", width=24)
        self.sort_box.pack(anchor="w")

    # --- Ausgabe & Vorgaben --------------------------------------------
    def _register_ausgabe(self, karte) -> None:
        c, F, pt = self.c, self.F, self.pt
        self._info(karte, "ps5pkg.opt_out_info")
        self._beschriftung(karte, "ps5pkg.opt_out_dir").pack(anchor="w")
        zeile = tk.Frame(karte, bg=c["bg_card"])
        zeile.pack(fill="x", pady=(4, 12))
        zeile.columnconfigure(0, weight=1)
        self.pw.Entry(zeile, textvariable=self.ziel_var, font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_primary"],
                      insertbackground=c["fg_primary"], relief="flat").grid(row=0, column=0, sticky="ew", ipady=3)
        self.pw.Button(zeile, text=self.t("ps5pkg.choose_target"), command=self._ziel_waehlen).grid(
            row=0, column=1, padx=(8, 0))
        self._beschriftung(karte, "ps5pkg.opt_out_temp_dir").pack(anchor="w")
        temp_zeile = tk.Frame(karte, bg=c["bg_card"])
        temp_zeile.pack(fill="x", pady=(4, 0))
        temp_zeile.columnconfigure(0, weight=1)
        self.pw.Entry(temp_zeile, textvariable=self.temp_ordner_var, font=(F, pt(10)), bg=c["bg_main"],
                      fg=c["fg_primary"], insertbackground=c["fg_primary"], relief="flat").grid(
            row=0, column=0, sticky="ew", ipady=3)
        self.pw.Button(temp_zeile, text=self.t("ps5pkg.choose_target"), command=self._temp_ordner_waehlen).grid(
            row=0, column=1, padx=(8, 0))
        tk.Label(karte, text=self.t("ps5pkg.opt_out_temp_dir_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 12))
        self._beschriftung(karte, "ps5pkg.opt_out_action").pack(anchor="w")
        self.aktion_box = self.pw.Combobox(karte, textvariable=self.aktion_var, values=list(self._aktionen().values()),
                                           state="readonly", width=24)
        self.aktion_box.pack(anchor="w", pady=(4, 12))
        self._beschriftung(karte, "ps5pkg.opt_out_format").pack(anchor="w")
        self.format_box = self.pw.Combobox(karte, textvariable=self.format_var, values=list(self._formate().values()),
                                           state="readonly", width=24)
        self.format_box.pack(anchor="w", pady=(4, 12))
        self._beschriftung(karte, "ps5pkg.opt_builder").pack(anchor="w")
        self.builder_box = self.pw.Combobox(karte, textvariable=self.builder_var, values=list(self._builder().values()),
                                            state="readonly", width=24)
        self.builder_box.pack(anchor="w", pady=(4, 0))
        tk.Label(karte, text=self.t("ps5pkg.opt_builder_hint"), font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"],
                 anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 12))
        self._beschriftung(karte, "ps5pkg.opt_passcode").pack(anchor="w")
        passcode_zeile = tk.Frame(karte, bg=c["bg_card"])
        passcode_zeile.pack(fill="x", pady=(4, 0))
        self.passcode_feld = self.pw.Entry(passcode_zeile, textvariable=self.passcode_var, font=(self.M, pt(10)),
                                           bg=c["bg_main"], fg=c["fg_primary"], insertbackground=c["fg_primary"],
                                           relief="flat", show="•")
        self.passcode_feld.pack(side="left", fill="x", expand=True, ipady=3)
        self.pw.Checkbutton(passcode_zeile, text=self.t("ps5pkg.opt_passcode_show"), variable=self.passcode_zeigen_var,
                            command=self._passcode_anzeige, font=(F, pt(9))).pack(side="left", padx=(10, 0))
        tk.Label(karte, text=self.t("ps5pkg.opt_passcode_hint"), font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"],
                 anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(4, 12))
        self._haken(karte, "ps5pkg.opt_open_after", self.oeffnen_var)

    def _passcode_anzeige(self) -> None:
        tk.Entry.configure(self.passcode_feld, show="" if self.passcode_zeigen_var.get() else "•")

    def _ziel_waehlen(self) -> None:
        gewaehlt = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.opt_out_dir"),
                                           initialdir=self.ziel_var.get() or None)
        if gewaehlt:
            self.ziel_var.set(os.path.normpath(gewaehlt))

    def _temp_ordner_waehlen(self) -> None:
        gewaehlt = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.opt_out_temp_dir"),
                                           initialdir=self.temp_ordner_var.get() or None)
        if gewaehlt:
            self.temp_ordner_var.set(os.path.normpath(gewaehlt))

    def _fakelib_waehlen(self) -> None:
        gewaehlt = filedialog.askdirectory(parent=self.win,
                                           title=self.t("ps5pkg.opt_build_backport_fakelib"),
                                           initialdir=self.backport_fakelib_var.get() or None)
        if gewaehlt:
            self.backport_fakelib_var.set(os.path.normpath(gewaehlt))

    # --- Wartung ---------------------------------------------------------
    def _register_wartung(self, karte) -> None:
        self._info(karte, "ps5pkg.opt_maint_info")
        for schluessel, befehl in (("ps5pkg.opt_export", self._exportieren), ("ps5pkg.opt_import", self._importieren),
                                   ("ps5pkg.opt_reset", self._zuruecksetzen)):
            self.pw.Button(karte, text=self.t(schluessel), command=befehl).pack(anchor="w", pady=(0, 8))

    # ------------------------------------------------------------------
    # Werte <-> Felder
    # ------------------------------------------------------------------
    def _felder_fuellen(self, werte: dict) -> None:
        self.rekursiv_var.set(bool(werte.get(opt.REKURSIV, opt.STANDARD[opt.REKURSIV])))
        self.start_var.set(bool(werte.get(opt.START_SCAN, opt.STANDARD[opt.START_SCAN])))
        self.cover_var.set(bool(werte.get(opt.COVER, opt.STANDARD[opt.COVER])))
        self.oeffnen_var.set(bool(werte.get(opt.OEFFNEN, opt.STANDARD[opt.OEFFNEN])))
        self.ziel_var.set(str(werte.get(opt.ZIEL, "")))
        self.temp_ordner_var.set(str(werte.get(opt.TEMP_ORDNER, "")))
        self.passcode_var.set(str(werte.get(opt.PASSCODE, "")))
        self.passcode_zeigen_var.set(False)
        if hasattr(self, "passcode_feld"):
            tk.Entry.configure(self.passcode_feld, show="•")
        self.sort_var.set(self._sortierungen().get(werte.get(opt.SORTIERUNG), self._sortierungen()["titel"]))
        self.aktion_var.set(self._aktionen().get(werte.get(opt.AKTION), self._aktionen()["umwandeln"]))
        self.format_var.set(self._formate().get(werte.get(opt.FORMAT), self._formate()["ffpfsc"]))
        self.builder_var.set(self._builder().get(werte.get(opt.BUILDER), self._builder()["lpp"]))
        self.kraken_modus_var.set(self._kraken_modi().get(
            werte.get(opt.KRAKEN_MODUS), self._kraken_modi()["kraken"]))
        self.kraken_stufe_var.set(str(werte.get(opt.KRAKEN_STUFE, 7)))
        self.kraken_kerne_var.set(str(werte.get(opt.KRAKEN_KERNE, 0)))
        self.playgo_chunks_var.set(str(werte.get(opt.PLAYGO_CHUNKS, 1)))
        self.deterministisch_var.set(bool(werte.get(opt.DETERMINISTISCH, False)))
        self.regen_playgo_var.set(bool(werte.get(opt.REGEN_PLAYGO, False)))
        self.backport_einbauen_var.set(bool(werte.get(opt.BACKPORT_EINBAUEN, False)))
        fw = werte.get(opt.BACKPORT_FIRMWARE, 0)
        self.backport_firmware_var.set(str(fw) if fw else (self.backport_fw_combo.cget("values")[0]
                                                            if hasattr(self, "backport_fw_combo")
                                                            and self.backport_fw_combo.cget("values") else "7"))
        self.backport_fakelib_var.set(str(werte.get(opt.BACKPORT_FAKELIB_ORDNER, "")))
        self.min_fw_var.set(str(werte.get(opt.MIN_FW_VERSION, "")))
        self.patch_modus_var.set(bool(werte.get(opt.PATCH_MODUS, False)))

    def werte_aus_feldern(self) -> dict:
        """Die Optionen, wie sie gerade im Dialog stehen (noch nicht gespeichert)."""
        bibliothek = [p for p in self.quellen + self.neue_quellen if p not in self.entfernt]
        return {
            opt.ORDNER: list(self.ordner),
            opt.BIBLIOTHEK: bibliothek,
            opt.REKURSIV: bool(self.rekursiv_var.get()),
            opt.START_SCAN: bool(self.start_var.get()),
            opt.COVER: bool(self.cover_var.get()),
            opt.OEFFNEN: bool(self.oeffnen_var.get()),
            opt.PASSCODE: self.passcode_var.get(),
            opt.BUILDER: self._schluessel_zu(self._builder(), self.builder_var.get(), "lpp"),
            opt.KRAKEN_MODUS: self._schluessel_zu(self._kraken_modi(), self.kraken_modus_var.get(), "kraken"),
            opt.KRAKEN_STUFE: max(-4, min(9, _int_safe(self.kraken_stufe_var.get(), 7))),
            opt.KRAKEN_KERNE: max(0, min(256, _int_safe(self.kraken_kerne_var.get(), 0))),
            opt.PLAYGO_CHUNKS: max(1, min(255, _int_safe(self.playgo_chunks_var.get(), 1))),
            opt.DETERMINISTISCH: bool(self.deterministisch_var.get()),
            opt.REGEN_PLAYGO: bool(self.regen_playgo_var.get()),
            opt.BACKPORT_EINBAUEN: bool(self.backport_einbauen_var.get()),
            opt.BACKPORT_FIRMWARE: max(0, min(20, _int_safe(self.backport_firmware_var.get(), 0))),
            opt.BACKPORT_FAKELIB_ORDNER: self.backport_fakelib_var.get().strip(),
            opt.MIN_FW_VERSION: self.min_fw_var.get().strip(),
            opt.PATCH_MODUS: bool(self.patch_modus_var.get()),
            opt.ZIEL: self.ziel_var.get().strip(),
            opt.TEMP_ORDNER: self.temp_ordner_var.get().strip(),
            opt.SORTIERUNG: self._schluessel_zu(self._sortierungen(), self.sort_var.get(), "titel"),
            opt.AKTION: self._schluessel_zu(self._aktionen(), self.aktion_var.get(), "umwandeln"),
            opt.FORMAT: self._schluessel_zu(self._formate(), self.format_var.get(), "ffpfsc"),
        }

    # ------------------------------------------------------------------
    # Wartung: Export, Import, Zuruecksetzen
    # ------------------------------------------------------------------
    def _exportieren(self) -> None:
        pfad = filedialog.asksaveasfilename(parent=self.win, title=self.t("ps5pkg.opt_export"), defaultextension=".json",
                                            initialfile=EXPORT_NAME, filetypes=[("JSON", "*.json")])
        if not pfad:
            return
        try:
            with open(pfad, "w", encoding="utf-8", newline="\n") as datei:
                json.dump(self.werte_aus_feldern(), datei, ensure_ascii=False, indent=1)
                datei.write("\n")
        except OSError as exc:
            messagebox.showerror(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_export_failed", grund=str(exc)),
                                 parent=self.win)
            return
        self.f._status(self.t("ps5pkg.opt_exported", pfad=pfad))

    def _importieren(self) -> None:
        pfad = filedialog.askopenfilename(parent=self.win, title=self.t("ps5pkg.opt_import"),
                                          filetypes=[("JSON", "*.json"), ("*", "*.*")])
        if not pfad:
            return
        try:
            with open(pfad, "r", encoding="utf-8-sig") as datei:
                daten = json.load(datei)
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_import_failed", grund=str(exc)),
                                 parent=self.win)
            return
        gueltig, probleme = opt.importieren_pruefen(daten)
        if not gueltig:
            messagebox.showerror(self.t("ps5pkg.window_title"),
                                 self.t("ps5pkg.opt_import_failed", grund="\n".join(probleme)), parent=self.win)
            return
        diff = opt.unterschiede(self.werte_aus_feldern(), gueltig)
        if not diff:
            messagebox.showinfo(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_import_same"), parent=self.win)
            return
        text = "\n".join(diff[:14] + (["…"] if len(diff) > 14 else []) + ([""] + probleme[:6] if probleme else []))
        if not messagebox.askyesno(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_import_confirm", liste=text),
                                   parent=self.win):
            return
        neu = self.werte_aus_feldern()
        neu.update(gueltig)
        if opt.ORDNER in gueltig:
            self.ordner = list(gueltig[opt.ORDNER])
        if opt.BIBLIOTHEK in gueltig:
            bekannt = set(self.quellen)
            self.neue_quellen = [p for p in gueltig[opt.BIBLIOTHEK] if p not in bekannt]
        self._felder_fuellen(neu)
        self._liste_zeigen()
        self.f._status(self.t("ps5pkg.opt_imported"))

    def _zuruecksetzen(self) -> None:
        if not messagebox.askyesno(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_reset_confirm"), parent=self.win):
            return
        self._felder_fuellen(opt.zuruecksetzen_werte())
        self.f._status(self.t("ps5pkg.opt_reset_done"))

    # ------------------------------------------------------------------
    # Speichern / Schliessen
    # ------------------------------------------------------------------
    def speichern(self) -> None:
        if not opt.passcode_gueltig(self.passcode_var.get()):
            messagebox.showerror(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_passcode_invalid"), parent=self.win)
            self.zeigen("ausgabe")
            self.passcode_feld.focus_set()
            return
        werte = self.werte_aus_feldern()
        ziel = werte[opt.ZIEL]
        if ziel and not os.path.isdir(ziel):
            if not messagebox.askyesno(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_target_missing", pfad=ziel),
                                       parent=self.win):
                return
        try:
            self.f.optionen_anwenden(werte, self.aktuell, list(self.entfernt), list(self.neue_quellen))
        except Exception:  # noqa: BLE001
            logger.exception("Optionen speichern")
            messagebox.showerror(self.t("ps5pkg.window_title"), self.t("ps5pkg.opt_save_failed"), parent=self.win)
            return
        self.schliessen()

    def schliessen(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if getattr(self.f, DIALOG_ATTRIBUT, None) is self:
            setattr(self.f, DIALOG_ATTRIBUT, None)
