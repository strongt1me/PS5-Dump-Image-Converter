# -*- coding: utf-8 -*-
"""Die Einbau-Karte der Seite 7 (PKG / FPKG): dieselben Felder wie die Karte der Aufgaben 1 bis 6.

Nutzerwunsch 17.11.2026: Die Seite soll aussehen wie die Aufgaben 1 bis 6 - KOMPRESSION (PFS), WORKER-THREADS, PRUEFUNG und
BEIM ERSTELLEN EINBAUEN mit AMPR EMU (Fassung, Methode, Packverfahren, Packstufe, vollstaendige Pruefung), PlayGo, DLC EMU
und BACKPORT -, damit niemand lange suchen muss. Dazu die Pruefung der Quelle: was Dump Forge im Spiel gefunden hat und was
davon fehlt (:mod:`ps5_validator.utils.quellbericht`).

Die Felder sind **Zwillinge** der Felder im Hauptfenster: dieselben Tk-Variablen (``ampr_integrate_var``, ``ampr_methode_var``
usw.) und dieselben Befehle (``_on_integration_changed``, ``_ampr_pack_gewaehlt`` usw.). Eine Wahl hier ist also eine Wahl in
den Aufgaben 1 bis 6 und umgekehrt, und der Lauf, der aus diesem Fenster an Aufgabe 1 uebergeben wird, liest genau diese
Kaestchen. Was die Auswahllisten anbieten und ob ein Feld gesperrt ist, entscheidet das Hauptfenster (``_on_integration_changed``,
``_ampr_pack_combo_schalten``, ``_ampr_stufe_combo_schalten``); :meth:`EinbauKarte.abgleichen` uebernimmt es im Takt des
Fensters - die Regeln stehen so nur einmal da.

Aufbau (Platz ist knapp: die Seite rollt nicht, das Protokoll nimmt den Rest): KOMPRESSION, WORKER und PRUEFUNG stehen rechts
neben ZIELFORMAT (:meth:`kopf_bauen`, wie im Hauptfenster); darunter links BEIM ERSTELLEN EINBAUEN, rechts davon die Pruefung
der Quelle. Die Zeile mit Packverfahren, Packstufe und vollstaendiger Pruefung erscheint, wenn AMPR EMU angehakt ist.
"""
from __future__ import annotations

import logging
import sys
import tkinter as tk
from typing import Any

from ps5_validator.utils import quellbericht as qb

logger = logging.getLogger(__name__)

#: Die Felder mit Auswahlliste: Name -> (Variable im Hauptfenster, Liste dort, Breite in Zeichen, Befehl dort nach der Wahl,
#: Kurzinfo dort (oder ``""``), Schluessel der festen Kurzinfo hier (oder ``""``)).
COMBOS = {
    "kompression": ("compression_level_var", "compression_combo", 15, "_on_compression_level_changed",
                    "_kompression_tooltip", "main.kompression_hint"),
    "pruefung": ("verify_var", "verify_combo", 12, "_on_verify_stufe_changed", "", "verify.hint"),
    "version": ("ampr_version_var", "ampr_version_combo", 14, "_ampr_version_gewaehlt", "", ""),
    "methode": ("ampr_methode_var", "ampr_methode_combo", 9, "_ampr_methode_gewaehlt", "", "ampr_pack.methode_hint"),
    "packverfahren": ("_ampr_pack_var", "ampr_pack_combo", 9, "_ampr_pack_gewaehlt", "_ampr_pack_tooltip",
                      "ampr_pack.verfahren_hint"),
    "packstufe": ("_ampr_stufe_var", "ampr_stufe_combo", 16, "_ampr_stufe_gewaehlt", "_ampr_stufe_tooltip",
                  "ampr_pack.stufe_hint"),
    "backport_fw": ("backport_fw_var", "backport_fw_combo", 4, "_backport_fw_gewaehlt", "", ""),
}

#: Die Kaestchen: Name -> (Variable im Hauptfenster, Kaestchen dort, Schluessel des Texts, fett, Befehl dort,
#: Kurzinfo dort (oder ``""``), Schluessel der festen Kurzinfo hier).
HAKEN = {
    "ampr": ("ampr_integrate_var", "ampr_integrate_check", "main.integrate_ampr", True, "_on_integration_changed", "",
             "main.integrate_ampr_hint"),
    "voll": ("_ampr_voll_var", "ampr_voll_check", "ampr_pack.voll_pruefen", False, "_ampr_voll_gewaehlt",
             "_ampr_voll_tooltip", "ampr_pack.voll_pruefen_hint"),
    "playgo": ("ampr_playgo_var", "ampr_playgo_check", "main.integrate_playgo", False, "_on_integration_changed", "",
               "ampr.lib_hint"),
    "dlc": ("dlc_integrate_var", "dlc_integrate_check", "main.integrate_dlc", True, "_on_integration_changed", "",
            "main.integrate_dlc_hint"),
    "backport": ("backport_integrate_var", "backport_integrate_check", "main.integrate_backport", True,
                 "_on_integration_changed", "", "main.integrate_backport_hint"),
}


def _liste(widget: Any, wert: Any) -> tuple:
    """Eine Werteliste von ``ttk.Combobox`` als Tupel (Tk liefert je nach Fassung ein Tupel oder einen Tcl-String)."""
    if isinstance(wert, str):
        try:
            return tuple(str(w) for w in widget.tk.splitlist(wert))
        except tk.TclError:
            return ()
    return tuple(str(w) for w in (wert or ()))


class EinbauKarte:
    """Die Felder und die Pruefung der Quelle als ein Abschnitt (``rahmen``) der Seite."""

    def __init__(self, fenster, eltern: tk.Misc) -> None:
        self.f = fenster
        self.g = fenster.g
        c, F, pt = fenster.c, fenster.F, fenster.pt
        self._c = c
        self._gilt = True
        self._komp_wirkt = True
        self.felder: dict[str, Any] = {}            # Name -> Feld hier (Combobox, Kaestchen, Drehknopf)
        self._kurzinfos: dict[str, Any] = {}        # Name -> Kurzinfo hier
        g = self.g

        self.rahmen = tk.Frame(eltern, bg=c["bg_main"])
        self.rahmen.columnconfigure(1, weight=1)

        # -- links: BEIM ERSTELLEN EINBAUEN ---------------------------------------------------------------------------
        links = tk.Frame(self.rahmen, bg=c["bg_main"])
        links.grid(row=0, column=0, sticky="nw")
        self._beschriftung(links, g._t("main.integrate_label")).pack(anchor="w", pady=(0, 5))
        zeile = self._zeile(links)
        self._haken_bauen(zeile, "ampr")
        self._combo_bauen(zeile, "version", links=10)
        self._combo_bauen(zeile, "methode", links=10)
        self._pack_zeile = self._zeile(links, einzug=22)       # erscheint, sobald AMPR EMU angehakt ist
        self._combo_bauen(self._pack_zeile, "packverfahren", links=0)
        self._combo_bauen(self._pack_zeile, "packstufe", links=10)
        self._haken_bauen(self._pack_zeile, "voll", links=14)
        self._pack_zeile.pack_forget()
        self._pack_sichtbar = False
        self._zeile3 = self._zeile(links)
        self._haken_bauen(self._zeile3, "playgo")
        self._haken_bauen(self._zeile3, "dlc", links=18)
        self._haken_bauen(self._zeile3, "backport", links=18)
        self._combo_bauen(self._zeile3, "backport_fw", links=6)

        # -- rechts: PRUEFUNG DER QUELLE --------------------------------------------------------------------------------
        rechts = tk.Frame(self.rahmen, bg=c["bg_main"])
        rechts.grid(row=0, column=1, sticky="nsew", padx=(26, 0))
        self._beschriftung(rechts, fenster.t("ps5pkg.einbau_pruefung")).pack(anchor="w", pady=(0, 5))
        self.bericht = rechts
        self._zeilen_rahmen = tk.Frame(rechts, bg=c["bg_main"])
        self._zeilen_rahmen.pack(fill="x")
        self._bericht_zeilen: list[tuple[tk.Frame, tk.Label, tk.Label]] = []
        self.status = tk.Label(rechts, text="", font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"], anchor="w",
                               justify="left", wraplength=320)
        self.status.pack(fill="x")

        # Hinweis, wenn der Einbau gerade nichts bewirkt (Paketbau, Extrahieren, Pruefen, auf die PS5 entpacken)
        self.hinweis = tk.Label(self.rahmen, text=fenster.t("ps5pkg.einbau_nur_abbild"), font=(F, pt(9)), bg=c["bg_main"],
                                fg=c.get("fg_warning", "#f0a32e"), anchor="w", justify="left", wraplength=520)
        self.hinweis.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.hinweis.grid_remove()
        self._hinweis_sichtbar = False

        self.rahmen.bind("<Configure>", lambda e: self._umbruch(e.width), add="+")
        rechts.bind("<Configure>", lambda e: self._umbruch_bericht(e.width), add="+")
        self.bericht_setzen(None, fenster.t("bericht.keine_quelle"))
        self.abgleichen(True, True)

    # ------------------------------------------------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------------------------------------------------
    def kopf_bauen(self, eltern: tk.Misc) -> None:
        """Legt KOMPRESSION (PFS), WORKER-THREADS und PRUEFUNG in ``eltern`` an (von links nach rechts, neben ZIELFORMAT).

        Wie im Hauptfenster stehen die drei in einer Zeile mit dem Zielformat; das spart eine ganze Zeile Hoehe.
        """
        g, c = self.g, self._c
        for name, titel in (("kompression", "main.compression_label"), ("worker", "main.worker_label"),
                            ("pruefung", "main.verify_label")):
            if name == "worker" and getattr(g, "worker_count_var", None) is None:
                continue
            if name != "worker" and not self._combo_moeglich(name):
                continue
            block = tk.Frame(eltern, bg=c["bg_main"])
            block.pack(side="left", anchor="n", padx=(22, 0))
            self._beschriftung(block, g._t(titel)).pack(anchor="w", pady=(0, 5))
            if name == "worker":
                knopf = g._fenster_drehknopf(block, g.worker_count_var, 1, g._worker_obergrenze(),
                                             hintergrund=c["bg_main"], command=g._on_worker_count_changed)
                knopf.pack(anchor="w")
                self.felder["worker"] = knopf
            else:
                self._combo(block, name).pack(anchor="w")
        self.abgleichen(self._gilt, self._komp_wirkt)

    def _beschriftung(self, eltern, text: str) -> tk.Label:
        return tk.Label(eltern, text=text.upper(), font=(self.f.F, self.f.pt(9), "bold"), bg=self._c["bg_main"],
                        fg=self._c["fg_primary"], anchor="w")

    def _zeile(self, eltern, einzug: int = 0) -> tk.Frame:
        zeile = tk.Frame(eltern, bg=self._c["bg_main"])
        zeile.pack(fill="x", anchor="w", padx=(einzug, 0), pady=(0, 5))
        return zeile

    def _combo_moeglich(self, name: str) -> bool:
        variable, haupt = COMBOS[name][0], COMBOS[name][1]
        return getattr(self.g, variable, None) is not None and getattr(self.g, haupt, None) is not None

    def _combo(self, eltern, name: str):
        variable, haupt, breite, befehl, kurzinfo, tipp = COMBOS[name]
        g = self.g
        quelle = getattr(g, haupt)
        feld = g._pw.Combobox(eltern, textvariable=getattr(g, variable), state="readonly", width=breite,
                              values=_liste(quelle, quelle.cget("values")), font=(self.f.F, self.f.pt(9)))
        feld.bind("<<ComboboxSelected>>", lambda _e, n=befehl: self._befehl(n))
        self.felder[name] = feld
        if tipp:
            self._kurzinfos[name] = self._tooltip(feld, tipp)
        return feld

    def _tooltip(self, feld, schluessel: str):
        """Eine Kurzinfo am Feld - **nicht** ueber ``g._tooltip``: Das Hauptfenster haelt jede so angelegte Kurzinfo samt Feld fuer
        immer fest (Liste ``_tooltip_schluessel``); ein Nebenfenster liesse so bei jedem Schliessen Felder und Bilder stehen
        (``test_fenster_leck``: je Fenster 4 GDI-Objekte). Die Kurzinfo stirbt hier mit dem Feld."""
        klasse = getattr(sys.modules.get(type(self.g).__module__), "DelayedTooltip", None)
        if klasse is None:
            return None
        return klasse(feld, self.g._t(schluessel), delay_ms=900, wraplength=430)

    def _combo_bauen(self, zeile, name: str, links: int = 0) -> None:
        if self._combo_moeglich(name):
            self._combo(zeile, name).pack(side="left", padx=(links, 0))

    def _haken_bauen(self, zeile, name: str, links: int = 0) -> None:
        variable, haupt, text, fett, befehl, kurzinfo, tipp = HAKEN[name]
        g = self.g
        if getattr(g, variable, None) is None or getattr(g, haupt, None) is None:
            return
        schrift = (self.f.F, self.f.pt(9), "bold") if fett else (self.f.F, self.f.pt(9))
        feld = g._pw.Checkbutton(zeile, text=g._t(text), variable=getattr(g, variable),
                                 command=lambda n=befehl: self._befehl(n), font=schrift)
        feld.pack(side="left", padx=(links, 0))
        self.felder[name] = feld
        self._kurzinfos[name] = self._tooltip(feld, tipp)

    def _befehl(self, name: str) -> None:
        """Ruft den Befehl des Hauptfensters (er speichert und sperrt dort) und zieht danach die Felder hier nach."""
        befehl = getattr(self.g, name, None)
        try:
            if callable(befehl):
                befehl()
        except Exception:  # noqa: BLE001 - wie Tk: ueber den Meldeweg des Programms, die Karte bleibt bedienbar
            logger.exception("Befehl %s der Einbau-Karte", name)
        self.abgleichen(self._gilt, self._komp_wirkt)

    def _umbruch(self, breite: int) -> None:
        self.hinweis.configure(wraplength=max(160, breite - 6))

    def _umbruch_bericht(self, breite: int) -> None:
        ziel = max(140, breite - 30)
        for _zeile, _marke, text in self._bericht_zeilen:
            text.configure(wraplength=ziel)
        self.status.configure(wraplength=max(140, breite - 4))

    # ------------------------------------------------------------------------------------------------------------
    # Abgleich mit dem Hauptfenster
    # ------------------------------------------------------------------------------------------------------------
    def abgleichen(self, gilt: bool, komp_wirkt: bool) -> None:
        """Uebernimmt Auswahllisten, Sperren und Kurzinfos der Felder des Hauptfensters.

        Args:
            gilt: Der Einbau wirkt bei dem, was die Seite gerade tut (Umwandeln in ein Abbild). Sonst sind die Felder
                gesperrt und der Hinweis steht da - ein Paket nimmt den Einbau nicht auf.
            komp_wirkt: Die Kompressionsstufe wirkt beim gewaehlten Format (nur der Container ``.ffpfsc``).
        """
        self._gilt, self._komp_wirkt = gilt, komp_wirkt
        g = self.g
        for name, feld in self.felder.items():
            if name == "worker":
                continue
            if name in COMBOS:
                haupt, kurzinfo = getattr(g, COMBOS[name][1], None), COMBOS[name][4]
            else:
                haupt, kurzinfo = getattr(g, HAKEN[name][1], None), HAKEN[name][5]
            if haupt is None:
                continue
            try:
                if name in COMBOS:
                    werte = _liste(haupt, haupt.cget("values"))
                    if werte != tuple(feld.values):
                        feld.configure(values=werte)
                frei = gilt and (komp_wirkt if name == "kompression" else True)
                ziel = str(haupt.cget("state")) if frei else "disabled"
                if str(feld.cget("state")) != ziel:
                    feld.configure(state=ziel)
                quelle = getattr(g, kurzinfo, None) if kurzinfo else None
                eigene = self._kurzinfos.get(name)
                if quelle is not None and eigene is not None and getattr(quelle, "text", None) is not None:
                    eigene.text = quelle.text
            except tk.TclError as exc:
                logger.debug("Einbau-Feld %s nicht abgleichbar: %s", name, exc)
        try:
            self._sichtbarkeit_setzen(gilt)
        except tk.TclError as exc:
            logger.debug("Sichtbarkeit der Einbau-Karte: %s", exc)

    def _sichtbarkeit_setzen(self, gilt: bool) -> None:
        """Der Hinweis nur, wenn der Einbau nichts bewirkt; die Zeile der Asset-Packs nur bei angehaktem AMPR EMU."""
        if gilt == self._hinweis_sichtbar:
            self._hinweis_sichtbar = not gilt
            if gilt:
                self.hinweis.grid_remove()
            else:
                self.hinweis.grid()
        ampr = getattr(self.g, "ampr_integrate_var", None)
        try:
            an = bool(ampr.get()) if ampr is not None else False
        except tk.TclError:
            an = False
        if an != self._pack_sichtbar and self._pack_zeile.winfo_children():
            self._pack_sichtbar = an
            if an:
                self._pack_zeile.pack(fill="x", anchor="w", padx=(22, 0), pady=(0, 5), before=self._zeile3)
            else:
                self._pack_zeile.pack_forget()

    # ------------------------------------------------------------------------------------------------------------
    # Pruefung der Quelle
    # ------------------------------------------------------------------------------------------------------------
    def bericht_setzen(self, zeilen: "list[qb.Zeile] | None", text: str = "") -> None:
        """Zeigt die Zeilen der Pruefung - oder, ohne Zeilen, nur ``text`` (noch keine Quelle, wird geprueft, nicht pruefbar)."""
        c, F, pt = self._c, self.f.F, self.f.pt
        zeilen = zeilen or []
        while len(self._bericht_zeilen) < len(zeilen):
            rahmen = tk.Frame(self._zeilen_rahmen, bg=c["bg_main"])
            marke = tk.Label(rahmen, text="●", font=(F, pt(8)), bg=c["bg_main"], width=2, anchor="w")
            marke.pack(side="left", anchor="n")
            beschriftung = tk.Label(rahmen, text="", font=(F, pt(9)), bg=c["bg_main"], anchor="w", justify="left",
                                    wraplength=300)
            beschriftung.pack(side="left", fill="x", expand=True)
            self._bericht_zeilen.append((rahmen, marke, beschriftung))
        farben = {qb.STUFE_OK: c.get("fg_success", "#3fc1c9"), qb.STUFE_FEHLT: c.get("fg_warning", "#f5c542"),
                  qb.STUFE_HINWEIS: c["fg_secondary"]}
        for nr, (rahmen, marke, beschriftung) in enumerate(self._bericht_zeilen):
            if nr < len(zeilen):
                z = zeilen[nr]
                marke.configure(fg=farben.get(z.stufe, c["fg_secondary"]))
                beschriftung.configure(text=z.text,
                                       fg=c.get("fg_warning", "#f5c542") if z.stufe == qb.STUFE_FEHLT else c["fg_primary"])
                if not rahmen.winfo_manager():
                    rahmen.pack(fill="x", anchor="w")
            elif rahmen.winfo_manager():
                rahmen.pack_forget()
        self.status.configure(text=text)
        if text and not self.status.winfo_manager():
            self.status.pack(fill="x")
        elif not text and self.status.winfo_manager():
            self.status.pack_forget()
