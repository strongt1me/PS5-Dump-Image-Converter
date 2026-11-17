# -*- coding: utf-8 -*-
"""Die Einbau-Karte der Seite 7 (PKG / FPKG): dieselben Felder in derselben Anordnung wie die Karte der Aufgaben 1 bis 6.

Nutzerwunsch 17.11.2026: Die Seite soll aussehen wie die Aufgaben 1 bis 6 - ZIELFORMAT, KOMPRESSION (PFS), WORKER und PRUEFUNG
in einer Zeile, jeweils mit einem Pfeil dazwischen, rechts daneben BEIM ERSTELLEN EINBAUEN in zwei Zeilen (AMPR EMU mit Methode
und Fassung, PlayGo, BACKPORT mit Firmware; darunter DLC EMU mit Packverfahren und Packstufe, vollstaendige Pruefung), unter dem
ZIELFORMAT ein Hinweis. Was im Spiel schon eingebaut ist, steht - wie dort - als ``[Pruefung]``-Zeilen im Protokoll, nicht in
einem eigenen Feld (Fenster: ``_bericht_aktualisieren``).

Die Felder sind **Zwillinge** der Felder im Hauptfenster: dieselben Tk-Variablen (``ampr_integrate_var``, ``ampr_methode_var``
usw.) und dieselben Befehle (``_on_integration_changed``, ``_ampr_pack_gewaehlt`` usw.). Eine Wahl hier ist also eine Wahl in
den Aufgaben 1 bis 6 und umgekehrt, und der Lauf, der aus diesem Fenster an Aufgabe 1 uebergeben wird, liest genau diese
Kaestchen. Was die Auswahllisten anbieten und ob ein Feld gesperrt ist, entscheidet das Hauptfenster (``_on_integration_changed``,
``_ampr_pack_combo_schalten``, ``_ampr_stufe_combo_schalten``); :meth:`EinbauKarte.abgleichen` uebernimmt es im Takt des
Fensters - die Regeln stehen so nur einmal da.

Aufbau (Nutzerwunsch 17.11.2026: "rechts neben Pruefung", wie bei Aufgabe 1): links die Zeile ``reihe`` (ZIELFORMAT baut das Fenster
selbst in sie hinein, :meth:`kopf_bauen` ergaenzt den Rest) mit dem Hinweis zum Zielformat darunter, rechts daneben die
Einbau-Gruppe. Die Pill-Felder dieses Fensters sind breiter als die des Hauptfensters; die Gruppe steht neben der Zeile deshalb in
drei Zeilen (PlayGo und BACKPORT samt Firmware in der dritten). Reicht die Breite nicht fuer die Zeile samt Gruppe, steht die
Gruppe darunter - in zwei Zeilen wie im Hauptfenster, wenn sie so passt (``_einbauzeile_passt_daneben`` dort), sonst in drei.
"""
from __future__ import annotations

import logging
import sys
import tkinter as tk
from typing import Any

logger = logging.getLogger(__name__)

#: Die Felder mit Auswahlliste: Name -> (Variable im Hauptfenster, Liste dort, Breite in Zeichen (die Pillen sind ``kompakt``:
#: Rand und Pfeil eng - wie die Felder der Aufgaben 1 bis 6; ``None``: so breit wie der laengste Wert), Befehl dort nach der Wahl,
#: Kurzinfo dort (oder ``""``), Schluessel der festen Kurzinfo hier (oder ``""``)).
COMBOS = {
    "kompression": ("compression_level_var", "compression_combo", 17, "_on_compression_level_changed",
                    "_kompression_tooltip", "main.kompression_hint"),
    "pruefung": ("verify_var", "verify_combo", 10, "_on_verify_stufe_changed", "", "verify.hint"),
    "version": ("ampr_version_var", "ampr_version_combo", 9, "_ampr_version_gewaehlt", "", ""),
    "methode": ("ampr_methode_var", "ampr_methode_combo", 8, "_ampr_methode_gewaehlt", "", "ampr_pack.methode_hint"),
    "packverfahren": ("_ampr_pack_var", "ampr_pack_combo", 6, "_ampr_pack_gewaehlt", "_ampr_pack_tooltip",
                      "ampr_pack.verfahren_hint"),
    "packstufe": ("_ampr_stufe_var", "ampr_stufe_combo", 13, "_ampr_stufe_gewaehlt", "_ampr_stufe_tooltip",
                  "ampr_pack.stufe_hint"),
    "backport_fw": ("backport_fw_var", "backport_fw_combo", 2, "_backport_fw_gewaehlt", "", ""),
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

#: Die Pfeile: Name -> Feld rechts davon (wie ``_PFEILE_PAARE`` im Hauptfenster; gesperrt wird der Pfeil blasser gezeichnet).
PFEILE = {"kompression": "kompression", "worker": "worker", "pruefung": "pruefung", "methode": "version",
          "pack": "packstufe"}

#: Luft zwischen der Zeile links (ZIELFORMAT bis PRUEFUNG) und der Einbau-Gruppe rechts daneben (wie ``_ZEILE_ABSTAND_GRUPPE``).
GRUPPE_LUFT = 20
#: Hoechstbreite, in der der Hinweis zum Zielformat umbricht (Pixel) - wie im Hauptfenster (``_hinweisbreite_setzen``: 560).
HINWEIS_MAX = 560


def _liste(widget: Any, wert: Any) -> tuple:
    """Eine Werteliste von ``ttk.Combobox`` als Tupel (Tk liefert je nach Fassung ein Tupel oder einen Tcl-String)."""
    if isinstance(wert, str):
        try:
            return tuple(str(w) for w in widget.tk.splitlist(wert))
        except tk.TclError:
            return ()
    return tuple(str(w) for w in (wert or ()))


class EinbauKarte:
    """Die Zeile mit ZIELFORMAT bis PRUEFUNG, der Hinweis darunter und BEIM ERSTELLEN EINBAUEN als ein Abschnitt (``rahmen``)."""

    def __init__(self, fenster, eltern: tk.Misc) -> None:
        self.f = fenster
        self.g = fenster.g
        c, F, pt = fenster.c, fenster.F, fenster.pt
        self._c = c
        self._gilt = True
        self._komp_wirkt = True
        self.felder: dict[str, Any] = {}            # Name -> Feld hier (Combobox, Kaestchen, Drehknopf)
        self._kurzinfos: dict[str, Any] = {}        # Name -> Kurzinfo hier
        self._pfeile: dict[str, Any] = {}           # Name -> Pfeil (siehe PFEILE)
        self._neben: "bool | None" = None
        self._schmal = False                        # PlayGo und BACKPORT in einer dritten Zeile (statt in Zeile 1)
        self._eng = False                           # das Feld ZIELFORMAT ist schmaler gemacht (``_reihe_anpassen``)
        self._format_breit = 0                      # seine Breite davor (Pixel)
        self._format_zeichen: "int | None" = None   # und sein Breitenwert in Zeichen davor
        bg = c["bg_main"]

        self.rahmen = tk.Frame(eltern, bg=bg)
        # links die Zeile ZIELFORMAT -> KOMPRESSION -> WORKER -> PRUEFUNG mit dem Hinweis zum Zielformat darunter, rechts daneben
        # BEIM ERSTELLEN EINBAUEN - wie bei den Aufgaben 1 bis 6 (``_anordnen``)
        self.reihe = tk.Frame(self.rahmen, bg=bg)
        self.reihe.grid(row=0, column=0, sticky="nw")
        self.format_hinweis = tk.Label(self.rahmen, text="", font=(F, pt(9)), bg=bg, fg=c["fg_secondary"], anchor="nw",
                                       justify="left", wraplength=HINWEIS_MAX)
        self.rechts = tk.Frame(self.rahmen, bg=bg)
        self._einbau_bauen(self.rechts)
        self._schmal_setzen(True)
        self._anordnen(True)

        self.rahmen.bind("<Configure>", self._platz_pruefen, add="+")
        self.reihe.bind("<Configure>", lambda e: self.format_hinweis.configure(wraplength=max(200, min(HINWEIS_MAX, e.width))),
                        add="+")
        self.abgleichen(True, True)

    # ------------------------------------------------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------------------------------------------------
    def kopf_bauen(self, format_titel: tk.Misc, format_feld: tk.Misc) -> None:
        """Legt ZIELFORMAT (das Fenster baut Beschriftung und Feld selbst in :attr:`reihe`) und dahinter KOMPRESSION (PFS),
        WORKER und PRUEFUNG in die Zeile - je mit einem Pfeil davor, wie im Hauptfenster."""
        g = self.g
        reihe = self.reihe
        format_titel.grid(row=0, column=0, sticky="w", pady=(0, 5))
        format_feld.grid(row=1, column=0, sticky="w")
        spalte = 1
        for name, titel in (("kompression", "main.compression_label"), ("worker", "main.worker_label"),
                            ("pruefung", "main.verify_label")):
            if name == "worker" and getattr(g, "worker_count_var", None) is None:
                continue
            if name != "worker" and not self._combo_moeglich(name):
                continue
            pfeil = self._pfeil(reihe, name)
            if pfeil is not None:
                pfeil.grid(row=1, column=spalte, padx=(2, 2))
            self._beschriftung(reihe, g._t(titel)).grid(row=0, column=spalte + 1, sticky="w", pady=(0, 5))
            if name == "worker":
                knopf = g._fenster_drehknopf(reihe, g.worker_count_var, 1, g._worker_obergrenze(),
                                             hintergrund=self._c["bg_main"], command=g._on_worker_count_changed)
                knopf.grid(row=1, column=spalte + 1, sticky="w")
                self.felder["worker"] = knopf
            else:
                self._combo(reihe, name).grid(row=1, column=spalte + 1, sticky="w")
            spalte += 2
        self.abgleichen(self._gilt, self._komp_wirkt)

    def _einbau_bauen(self, gruppe: tk.Frame) -> None:
        """BEIM ERSTELLEN EINBAUEN: Zeile 1 AMPR EMU, Methode, Pfeil, Fassung, PlayGo, BACKPORT, Firmware; Zeile 2 DLC EMU,
        Packverfahren, Pfeil, Packstufe, vollstaendige Pruefung - in einem Raster, damit beide Zeilen buendig stehen."""
        g = self.g
        self._beschriftung(gruppe, g._t("main.integrate_label")).grid(row=0, column=0, columnspan=7, sticky="w", pady=(0, 5))
        self._haken_bauen(gruppe, "ampr", 1, 0)
        self._combo_bauen(gruppe, "methode", 1, 1, links=8)
        self._pfeil_setzen(gruppe, "methode", 1, 2)
        self._combo_bauen(gruppe, "version", 1, 3)
        self._haken_bauen(gruppe, "playgo", 1, 4, links=10)
        self._haken_bauen(gruppe, "backport", 1, 5, links=14)
        self._combo_bauen(gruppe, "backport_fw", 1, 6, links=6)
        self._haken_bauen(gruppe, "dlc", 2, 0, oben=8)
        self._combo_bauen(gruppe, "packverfahren", 2, 1, links=8, oben=8)
        self._pfeil_setzen(gruppe, "pack", 2, 2, oben=8)
        # Die Packstufe reicht ueber zwei Spalten (hinter der Fassung und unter PlayGo), die Pruefung steht hinter ihr: Wie bei den
        # Aufgaben 1 bis 6 schiebt die laengere Zeile 2 die Zeile 1 nicht nach rechts.
        self._combo_bauen(gruppe, "packstufe", 2, 3, oben=8, spannt=2)
        self._haken_bauen(gruppe, "voll", 2, 5, links=10, oben=8, spannt=2)

    def _beschriftung(self, eltern, text: str) -> tk.Label:
        return tk.Label(eltern, text=text.upper(), font=(self.f.F, self.f.pt(9), "bold"), bg=self._c["bg_main"],
                        fg=self._c["fg_primary"], anchor="w")

    def _combo_moeglich(self, name: str) -> bool:
        variable, haupt = COMBOS[name][0], COMBOS[name][1]
        return getattr(self.g, variable, None) is not None and getattr(self.g, haupt, None) is not None

    def _combo(self, eltern, name: str):
        variable, haupt, breite, befehl, kurzinfo, tipp = COMBOS[name]
        g = self.g
        quelle = getattr(g, haupt)
        feld = g._pw.Combobox(eltern, textvariable=getattr(g, variable), state="readonly", width=breite,
                              values=_liste(quelle, quelle.cget("values")), font=(self.f.F, self.f.pt(9)), kompakt=True)
        feld.bind("<<ComboboxSelected>>", lambda _e, n=befehl: self._befehl(n))
        self.felder[name] = feld
        if tipp:
            self._kurzinfos[name] = self._tooltip(feld, tipp)
        return feld

    def _pfeil(self, eltern, name: str):
        """Ein Pfeil wie im Hauptfenster (``PackPfeil``); ohne ihn (Test ohne Hauptmodul) entfaellt er."""
        klasse = getattr(sys.modules.get(type(self.g).__module__), "PackPfeil", None)
        if klasse is None:
            return None
        pfeil = klasse(eltern, palette=lambda: self.g._COLORS, breite=12, hoehe=24, bg=self._c["bg_main"])
        self._pfeile[name] = pfeil
        return pfeil

    def _pfeil_setzen(self, gruppe, name: str, zeile: int, spalte: int, oben: int = 0) -> None:
        pfeil = self._pfeil(gruppe, name)
        if pfeil is not None:
            pfeil.grid(row=zeile, column=spalte, padx=(4, 4), pady=(oben, 0))

    def _tooltip(self, feld, schluessel: str):
        """Eine Kurzinfo am Feld - **nicht** ueber ``g._tooltip``: Das Hauptfenster haelt jede so angelegte Kurzinfo samt Feld fuer
        immer fest (Liste ``_tooltip_schluessel``); ein Nebenfenster liesse so bei jedem Schliessen Felder und Bilder stehen
        (``test_fenster_leck``: je Fenster 4 GDI-Objekte). Die Kurzinfo stirbt hier mit dem Feld."""
        klasse = getattr(sys.modules.get(type(self.g).__module__), "DelayedTooltip", None)
        if klasse is None:
            return None
        return klasse(feld, self.g._t(schluessel), delay_ms=900, wraplength=430)

    def _combo_bauen(self, gruppe, name: str, zeile: int, spalte: int, links: int = 0, oben: int = 0, spannt: int = 1) -> None:
        if self._combo_moeglich(name):
            self._combo(gruppe, name).grid(row=zeile, column=spalte, columnspan=spannt, sticky="w", padx=(links, 0),
                                           pady=(oben, 0))

    def _haken_bauen(self, gruppe, name: str, zeile: int, spalte: int, links: int = 0, oben: int = 0, spannt: int = 1) -> None:
        variable, haupt, text, fett, befehl, kurzinfo, tipp = HAKEN[name]
        g = self.g
        if getattr(g, variable, None) is None or getattr(g, haupt, None) is None:
            return
        schrift = (self.f.F, self.f.pt(9), "bold") if fett else (self.f.F, self.f.pt(9))
        feld = g._pw.Checkbutton(gruppe, text=g._t(text), variable=getattr(g, variable),
                                 command=lambda n=befehl: self._befehl(n), font=schrift)
        feld.grid(row=zeile, column=spalte, columnspan=spannt, sticky="w", padx=(links, 0), pady=(oben, 0))
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

    # ------------------------------------------------------------------------------------------------------------
    # Anordnung: die Einbau-Gruppe neben der Zeile - oder, wenn die Breite nicht reicht, darunter
    # ------------------------------------------------------------------------------------------------------------
    def _anordnen(self, neben: bool) -> None:
        """``neben``: die Gruppe steht rechts neben der Zeile (und dem Hinweis); sonst unter beiden."""
        if neben == self._neben:
            return
        self._neben = neben
        self.format_hinweis.grid(row=1, column=0, sticky="nw", pady=(6, 0))
        if neben:
            self.rechts.grid(row=0, column=1, rowspan=2, sticky="nw", padx=(GRUPPE_LUFT, 0), pady=0)
        else:
            self.rechts.grid(row=2, column=0, columnspan=2, sticky="nw", padx=0, pady=(12, 0))

    def _gruppe_breiten(self) -> "tuple[int, int]":
        """Die Breite der Gruppe (Pixel), wenn PlayGo und BACKPORT in Zeile 1 stehen, und wenn sie in einer dritten Zeile stehen.

        Aus den Wunschbreiten der Felder und den Abstaenden des Rasters - nicht aus dem, was gerade gelegt ist: So haengt die
        Entscheidung nicht davon ab, in welcher Form die Gruppe schon steht (sonst flackerte sie bei jeder Messung). Die
        Packstufe reicht ueber die Spalten 3 und 4, die Pruefung ueber 5 und 6: Sie schieben Zeile 1 nur, wenn sie dort nicht
        mehr Platz finden."""
        def w(name: str) -> int:
            feld = self.felder.get(name)
            return int(feld.winfo_reqwidth()) if feld is not None else 0
        pfeil = 20 if self._pfeile.get("methode") is not None else 0           # 12 px und je 4 px Luft
        links = max(w("ampr"), w("dlc")) + 8 + max(w("methode"), w("packverfahren")) + pfeil
        spalte3 = w("version")
        spalte4 = max(10 + w("playgo"), w("packstufe") - spalte3)               # PlayGo oder der Rest der Packstufe
        schmal = links + spalte3 + spalte4
        hinten = 14 + w("backport") + 6 + w("backport_fw")                      # Spalten 5 und 6
        breit = schmal + max(hinten, 10 + w("voll"))
        return breit + 4, schmal + 4

    def _platz_pruefen(self, _e=None) -> None:
        """Wohin mit der Gruppe? Rechts neben die Zeile in zwei Zeilen wie bei den Aufgaben 1 bis 6; reicht die Breite dafuer nicht,
        daneben in drei, dann darunter (in zwei Zeilen, wenn sie so passt, sonst in drei) - sonst ragte ihr Ende aus der Karte:
        unsichtbar und nicht anklickbar (``test_pkg_fpkg_seite``: Mindestgroesse)."""
        try:
            breite = self.rahmen.winfo_width()
            if breite <= 1:
                return
            self._reihe_anpassen(breite)
            breit, schmal = self._gruppe_breiten()
            reihe = self.reihe.winfo_reqwidth() + GRUPPE_LUFT
            if reihe + breit <= breite:                  # wie bei den Aufgaben 1 bis 6: zwei Zeilen rechts neben PRUEFUNG
                self._schmal_setzen(False)
                self._anordnen(True)
            elif reihe + schmal <= breite:               # daneben nur in drei Zeilen
                self._schmal_setzen(True)
                self._anordnen(True)
            else:                                        # darunter: zwei Zeilen, wenn sie so passen, sonst drei
                self._schmal_setzen(breit > breite)
                self._anordnen(False)
        except tk.TclError as exc:
            logger.debug("Platz der Einbau-Gruppe nicht messbar: %s", exc)

    #: Zeichen, auf die das Feld ZIELFORMAT schrumpft, wenn die Zeile bis PRUEFUNG sonst nicht in die Karte passt.
    FORMAT_ENG = 14

    def _reihe_anpassen(self, breite: int) -> None:
        """Passt die Zeile ZIELFORMAT bis PRUEFUNG nicht in die Karte (Mindestgroesse: 18 px zu breit, ``test_pkg_fpkg_seite``), wird das
        Feld ZIELFORMAT schmaler - nur dann; sonst richtet sich seine Breite nach dem laengsten Eintrag ("Auf die PS5 entpacken")."""
        box = getattr(self.f, "format_box", None)
        if box is None:
            return
        if not self._eng:
            if self.reihe.winfo_reqwidth() > breite:
                self._format_breit = box.winfo_reqwidth()
                self._format_zeichen = int(box.cget("width") or 0) or None
                box.configure(width=self.FORMAT_ENG)
                self._eng = True
        elif self.reihe.winfo_reqwidth() + (self._format_breit - box.winfo_reqwidth()) <= breite:
            box.configure(width=self._format_zeichen)                 # die Breite, mit der das Fenster das Feld angelegt hat
            self._eng = False

    #: Wo PlayGo, BACKPORT, die Firmware und die vollstaendige Pruefung stehen (Zeile, Spalte, Spalten, Luft links, Luft oben):
    #: breit wie im Hauptfenster (PlayGo, BACKPORT und Firmware in Zeile 1, die Pruefung hinter der Packstufe) - schmal, wenn
    #: die Gruppe neben die Zeile soll oder die Karte eng ist: BACKPORT samt Firmware und die Pruefung in einer dritten Zeile
    #: (die Pruefung unter der Packstufe, zu der sie gehoert).
    _BREIT = {"playgo": (1, 4, 1, 10, 0), "backport": (1, 5, 1, 14, 0), "backport_fw": (1, 6, 1, 6, 0),
              "voll": (2, 5, 2, 10, 8)}
    _SCHMAL = {"playgo": (1, 4, 1, 10, 0), "backport": (3, 0, 1, 0, 8), "backport_fw": (3, 1, 1, 8, 8),
               "voll": (3, 3, 3, 0, 8)}

    def _schmal_setzen(self, schmal: bool) -> None:
        if schmal == self._schmal:
            return
        self._schmal = schmal
        for name, (zeile, spalte, spannt, links, oben) in (self._SCHMAL if schmal else self._BREIT).items():
            feld = self.felder.get(name)
            if feld is not None:
                feld.grid_configure(row=zeile, column=spalte, columnspan=spannt, padx=(links, 0), pady=(oben, 0))

    def format_hinweis_setzen(self, text: str) -> None:
        """Der Hinweis unter dem ZIELFORMAT (wie ``format_info_label`` im Hauptfenster)."""
        if self.format_hinweis.cget("text") != text:
            self.format_hinweis.configure(text=text)

    # ------------------------------------------------------------------------------------------------------------
    # Abgleich mit dem Hauptfenster
    # ------------------------------------------------------------------------------------------------------------
    def abgleichen(self, gilt: bool, komp_wirkt: bool) -> None:
        """Uebernimmt Auswahllisten, Sperren und Kurzinfos der Felder des Hauptfensters.

        Args:
            gilt: Der Einbau wirkt bei dem, was die Seite gerade tut (Umwandeln in ein Abbild). Sonst sind die Felder
                gesperrt - ein Paket nimmt den Einbau nicht auf.
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
        self._pfeile_abgleichen()

    def _pfeile_abgleichen(self) -> None:
        """Ein Pfeil ist blass, wenn das Feld rechts von ihm gesperrt ist (wie im Hauptfenster)."""
        for name, pfeil in self._pfeile.items():
            feld = self.felder.get(PFEILE.get(name, ""))
            if feld is None:
                continue
            try:
                # Der Drehknopf des Workers hat keine Sperre - sein Pfeil bleibt, wie er ist.
                pfeil.setze_aktiv(True if name == "worker" else str(feld.cget("state")) != "disabled")
            except (tk.TclError, AttributeError) as exc:
                logger.debug("Pfeil %s nicht abgleichbar: %s", name, exc)
