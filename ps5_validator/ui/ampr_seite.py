# -*- coding: utf-8 -*-
"""Aufgabe 7 „AMPR EMU Manager“ als Seite im rechten Bereich der Ansicht UMWANDELN (seit 07.10.2026).

Bis v1.9.65 oeffnete der Knopf zwei Fenster nacheinander: ein rahmenloses Auswahlfenster (Ablageweg,
Methode) und danach das Fenster des Laufs mit Protokoll. Beides steht jetzt in **einer** Seite in der
Zelle (1, 1) - dort, wo sonst die Rollflaeche mit Quelle, Ziel und Protokoll liegt:

* **Auswahl:** Ablageweg (pro Spiel, global, Emulatoren), die beiden Methoden mit ihren Anleitungen.
* **Ablauf:** Geltungsbereich, was passiert, Protokoll; „CONFIG.INI“, „ERNEUT AUSFUEHREN“, Weg zurueck.

Die Arbeit macht weiter ``PS5ConverterGUI._ampr_gen_automatik``; sie bekommt das Hauptfenster als
Besitzer ihrer kurzen Rueckfragen (Ja/Nein, Fassungswahl, Spielordner). Das sind weiterhin Dialoge.
"""
from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from typing import Any

from ps5_validator.utils import shadowmount_generation as sm_gen

logger = logging.getLogger("PS5Converter.ui.ampr_seite")

SEITE_ATTRIBUT = "_ampr_seite"


def _haupt(gui):
    """Das Modul des Hauptprogramms (``pt``, Schriften, ``RoundedButton``)."""
    return sys.modules[type(gui).__module__]


class AmprSeite:
    """Die Seite: ein Rahmen, in dem Auswahl und Ablauf einander abloesen."""

    def __init__(self, gui) -> None:
        self.g = gui
        self.h = _haupt(gui)
        self.t = gui._t
        self.c = gui._COLORS
        self.generation = ""
        self.laeuft = False
        self.wegknoepfe: dict[str, Any] = {}
        self._bauen()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _bauen(self) -> None:
        g, h, c, t = self.g, self.h, self.c, self.t
        F, pt = h.UI_SCHRIFT, h.pt
        self.rahmen = tk.Frame(g.root, bg=c["bg_main"], padx=24, pady=18)

        kopf = tk.Frame(self.rahmen, bg=c["bg_main"])
        kopf.pack(fill="x")
        titel = tk.Label(kopf, text=t("ampr_auswahl.title"), font=(F, pt(15), "bold"),
                         bg=c["bg_main"], fg=c["fg_primary"], anchor="w")
        titel.pack(side="left")
        g._register_translatable(titel, "ampr_auswahl.title")
        self.zurueck = g._seitenpille(kopf, "ampr_seite.zurueck", self.zeigen_auswahl, klein=True)
        self.untertitel = tk.Label(self.rahmen, text="", font=(F, pt(9)), bg=c["bg_main"],
                                   fg=c["fg_secondary"], anchor="w", justify="left", wraplength=700)
        self.untertitel.pack(fill="x", pady=(4, 0))
        self.untertitel.bind("<Configure>", lambda e: self.untertitel.configure(wraplength=max(100, e.width - 8)))

        self.auswahl = tk.Frame(self.rahmen, bg=c["bg_main"])
        self.ablauf = tk.Frame(self.rahmen, bg=c["bg_main"])
        self._auswahl_bauen()
        self._ablauf_bauen()

    def _auswahl_bauen(self) -> None:
        g, h, c, t = self.g, self.h, self.c, self.t
        F, pt = h.UI_SCHRIFT, h.pt
        a = self.auswahl
        tk.Label(a, text=t("ampr_auswahl.ablage"), font=(F, pt(10), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x", pady=(16, 6))
        reihe = tk.Frame(a, bg=c["bg_main"])
        reihe.pack(fill="x")
        for kennung in g.ABLAGE_WEGE:
            knopf = h.RoundedButton(
                reihe, text="", command=(lambda k=kennung: self._weg_waehlen(k)),
                font=(F, pt(10), "bold"), bg=c["console_bg"], fg=c["fg_secondary"],
                activebackground=c["fg_accent"], activeforeground=c["bg_main"],
                outline=c["border"], radius=8, height=34, pille=True, breite_nach_text=True, polster_x=18)
            knopf.pack(side="left", padx=(0, 8))
            self.wegknoepfe[kennung] = knopf
        self.erklaerung = tk.Label(a, text="", font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                                   anchor="w", justify="left", wraplength=700)
        self.erklaerung.pack(fill="x", pady=(8, 4))
        self.erklaerung.bind("<Configure>", lambda e: self.erklaerung.configure(wraplength=max(100, e.width - 8)))

        tk.Label(a, text=t("ampr_seite.methode"), font=(F, pt(10), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x", pady=(18, 6))
        for schluessel, generation in (("titlebar.ampr_neu", sm_gen.NEU), ("titlebar.ampr_alt", sm_gen.ALT)):
            zeile = tk.Frame(a, bg=c["bg_main"])
            zeile.pack(fill="x", pady=(0, 8))
            g._seitenpille(zeile, schluessel, (lambda gen=generation: self.zeigen_ablauf(gen))).pack(side="left")
            g._seitenpille(zeile, "ampr_auswahl.anleitung", (lambda gen=generation: g._show_ampr_anleitung(gen)),
                           klein=True).pack(side="left", padx=(10, 0))
        self._wege_zeichnen()

    def _ablauf_bauen(self) -> None:
        g, h, c, t = self.g, self.h, self.c, self.t
        F, M, pt = h.UI_SCHRIFT, h.MONO_SCHRIFT, h.pt
        a = self.ablauf
        # Von unten nach oben: die Knopfreihe steht fest, das Protokoll nimmt den Rest.
        knoepfe = tk.Frame(a, bg=c["bg_main"])
        knoepfe.pack(side="bottom", fill="x", pady=(10, 0))
        self.config_knopf = g._seitenpille(knoepfe, "amprgen.btn_config", self._config)
        self.config_knopf.pack(side="left")
        self.start_knopf = g._seitenpille(knoepfe, "amprgen.btn_run", self._starten, akzent=True)
        self.start_knopf.pack(side="left", padx=(8, 0))

        gilt = tk.Frame(a, bg=c["bg_card"], padx=12, pady=8)
        gilt.pack(fill="x", pady=(14, 6))
        self.gilt_label = tk.Label(gilt, text="", font=(F, pt(9), "bold"), bg=c["bg_card"],
                                   fg=c["fg_primary"], anchor="w", justify="left")
        self.gilt_label.pack(fill="x")
        self.nicht_label = tk.Label(gilt, text="", font=(F, pt(9)), bg=c["bg_card"],
                                    fg=c["fg_secondary"], anchor="w", justify="left")
        self.nicht_label.pack(fill="x")
        was = tk.Label(a, text=t("amprgen.what_happens"), font=(F, pt(9), "bold"), bg=c["bg_main"],
                       fg=c["fg_primary"], anchor="w")
        was.pack(fill="x", pady=(8, 2))
        g._register_translatable(was, "amprgen.what_happens")
        self.was_label = tk.Label(a, text="", font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                                  anchor="w", justify="left", wraplength=700)
        self.was_label.pack(fill="x", pady=(0, 6))
        self.was_label.bind("<Configure>", lambda e: self.was_label.configure(wraplength=max(100, e.width - 8)))
        proto = tk.Label(a, text=t("amprgen.log"), font=(F, pt(9), "bold"), bg=c["bg_main"],
                         fg=c["fg_primary"], anchor="w")
        proto.pack(fill="x", pady=(4, 2))
        g._register_translatable(proto, "amprgen.log")
        karte = g._runde_seitenkarte(a, "console_bg", polster=(6, 6))
        karte.pack(fill="both", expand=True)
        self.feld = tk.Text(karte.innen, height=8, wrap="word", font=(M, pt(9)), bg=c["console_bg"],
                            fg=c["console_fg"], selectbackground=c["fg_accent"], relief="flat",
                            padx=10, pady=6, state="disabled")
        self.feld.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Auswahl
    # ------------------------------------------------------------------
    def _wege_zeichnen(self) -> None:
        """Hebt den gewaehlten Ablageweg hervor - farbig UND mit Haken (nicht nur ueber die Farbe)."""
        g, c, t = self.g, self.c, self.t
        aktuell = g._ampr_ablage_wahl()
        for kennung, knopf in self.wegknoepfe.items():
            beschriftung = t("ampr_auswahl.ablage_%s" % kennung)
            gewaehlt = kennung == aktuell
            knopf.config(text=("✓ " + beschriftung) if gewaehlt else beschriftung,
                         bg=c["fg_accent"] if gewaehlt else c["console_bg"],
                         fg=c["bg_main"] if gewaehlt else c["fg_secondary"])
        self.erklaerung.configure(text=t("ampr_auswahl.ablage_%s_why" % aktuell))

    def _weg_waehlen(self, kennung: str) -> None:
        self.g._ampr_ablage_merken(kennung)
        self._wege_zeichnen()

    def zeigen_auswahl(self) -> None:
        self.ablauf.pack_forget()
        self.zurueck.pack_forget()
        self.auswahl.pack(fill="both", expand=True)
        self.untertitel.configure(text=self.t("ampr_auswahl.hint"))
        self._wege_zeichnen()

    # ------------------------------------------------------------------
    # Ablauf
    # ------------------------------------------------------------------
    def zeigen_ablauf(self, generation: str, *, starten: bool = True) -> None:
        """Zeigt den Ablauf einer Methode und startet ihn von selbst (wie das Fenster davor)."""
        g, t = self.g, self.t
        if self.laeuft and generation != self.generation:
            # Ein Lauf ist noch nicht fertig: derselbe bleibt sichtbar, ein anderer startet nicht daneben.
            generation = self.generation
            starten = False
        neu = generation != self.generation
        self.generation = generation
        p = sm_gen.profil(generation, texte=g._smgen_texte())
        self.auswahl.pack_forget()
        self.ablauf.pack(fill="both", expand=True)
        self.zurueck.pack(side="right", anchor="n")
        self.untertitel.configure(text=t("amprgen.subtitle_%s" % generation))
        self.gilt_label.configure(text=t("amprgen.applies", value=p["gilt_fuer"]))
        self.nicht_label.configure(text=t("amprgen.not_for", value=p["nicht_fuer"]))
        self.was_label.configure(text=t(
            "amprgen.what_happens_text",
            folder=sm_gen.ablageordner(generation, sm_gen.ORT_BACKPORT if generation == sm_gen.NEU
                                       else sm_gen.ORT_SPIEL)))
        if neu:
            self.feld.configure(state="normal")
            self.feld.delete("1.0", "end")
            self.feld.configure(state="disabled")
            for falle in sm_gen.stolperfallen(generation, texte=g._smgen_texte()):
                self.protokoll("* " + falle)
        if starten and not self.laeuft:
            g._spaeter_im_fenster(g.root, self._starten)

    def protokoll(self, text: str) -> None:
        if not self.feld.winfo_exists():
            return
        self.feld.configure(state="normal")
        self.feld.insert("end", text + "\n")
        self.feld.see("end")
        self.feld.configure(state="disabled")

    def _melden(self, text: str) -> None:
        """Aus dem Arbeitsfaden ins Protokoll - immer ueber die Wurzel."""
        self.g._spaeter_im_fenster(self.g.root, self.protokoll, text)

    def _starten(self) -> None:
        if self.laeuft or not self.generation:
            return
        self.laeuft = True
        generation = self.generation
        self._start_sperren(True)
        self.protokoll("")
        self.protokoll("=" * 60)
        self.protokoll(self.t("amprgen.run_start"))

        def _lauf() -> None:
            try:
                self.g._ampr_gen_automatik(generation, self.g.root, self._melden)
            except Exception:  # noqa: BLE001 - ein Fehler gehoert ins Protokoll, nicht in den Faden
                logger.exception("AMPR-Ablauf")
                self._melden(self.t("amprgen.failed", error=sys.exc_info()[1]))
            finally:
                self.laeuft = False
                self.g._spaeter_im_fenster(self.g.root, self._start_sperren, False)

        threading.Thread(target=_lauf, daemon=True, name="ampr-ablauf").start()

    def _start_sperren(self, sperren: bool) -> None:
        for knopf in (self.start_knopf,):
            try:
                if knopf.winfo_exists():
                    knopf.configure(state="disabled" if sperren else "normal")
            except tk.TclError:
                pass

    def _config(self) -> None:
        """Der vorhandene Editor - vorbelegt mit den Schluesseln dieser Fassung."""
        g = self.g
        p = sm_gen.profil(self.generation or sm_gen.NEU, texte=g._smgen_texte())
        fassungswerte = {k: v for k, v in p["config_schluessel"] if v and k not in sm_gen.PFAD_SCHLUESSEL}
        vorgaben = dict(g._SHADOWMOUNT_DEFAULTS)
        vorgaben.update({k: v for k, v in p["config_schluessel"] if v})
        g._show_remote_ini_editor(self.t("remote_ini.shadowmount_title"), sm_gen.CONFIG_PFAD, sm_gen.DEBUG_LOG,
                                  vorgaben, "shadowmount", vorrang_werte=fassungswerte)


def seite(gui) -> AmprSeite:
    """Die Seite des Programms - beim ersten Zeigen gebaut."""
    vorhanden = getattr(gui, SEITE_ATTRIBUT, None)
    if vorhanden is None:
        vorhanden = AmprSeite(gui)
        setattr(gui, SEITE_ATTRIBUT, vorhanden)
    return vorhanden


def zeigen(gui, generation: str = "") -> AmprSeite:
    """Blendet die Seite im rechten Bereich ein; ohne ``generation`` die Auswahl (oder den laufenden Ablauf)."""
    s = seite(gui)
    gui._ampr_seite_einblenden(s.rahmen)
    if generation:
        s.zeigen_ablauf(generation)
    elif s.laeuft and s.generation:
        s.zeigen_ablauf(s.generation, starten=False)
    else:
        s.zeigen_auswahl()
    return s
