# -*- coding: utf-8 -*-
"""Das Fenster „Updates“ (seit v1.9.72): alle mitgelieferten Werkzeuge auf neuere Fassungen pruefen und holen.

Geoeffnet wird es vom Knopf **Updates** auf der Seite „Konsole & Payloads“. Der Druck auf diesen Knopf ist der
Netzzugriff (Regel seit v1.8.74: nur auf Knopfdruck): Das Fenster geht auf und fragt sofort jedes Projekt nach seiner
neuesten Freigabe. Danach steht jedes Werkzeug mit seiner mitgelieferten und der neuesten Fassung in einer Liste;
was ladbar und neuer ist, laesst sich ankreuzen und holen. Alles andere (Engines mit Anpassungen, Archive, Eigenes)
steht mit dem Urteil und dem Link zur Freigabe-Seite da.

Geholte Dateien landen in ``<Einstellungsordner>/Werkzeug-Updates/<Ort>/`` und ersetzen nie eine mitgelieferte
(:mod:`ps5_validator.utils.werkzeug_updates`). Jede Datei wird gegen Groesse und SHA-256 der Freigabe geprueft.

**Faeden:** Arbeitsfaeden fassen nie ein Widget oder eine Tk-Variable an, uebersetzen nichts und **kennen das Fenster
nicht** - sie halten nur ein :class:`_Postfach`, in das sie unter Sperre schreiben; ein Takt im Fensterfaden
(:meth:`UpdatesFenster._takt`) liest es (siehe ``project_tk_faden_variablen``). Faellt der letzte Verweis auf das Fenster
in einem Arbeitsfaden, ruft ``tk.Variable.__del__`` dort Tcl auf („main thread is not in main loop“).
"""
from __future__ import annotations

import logging
import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox
from typing import Callable

from ps5_validator.utils import plattform
from ps5_validator.utils import werkzeug_updates as wu

logger = logging.getLogger("PS5Converter.ui.updates_fenster")

FENSTER_ATTRIBUT = "_updates_fenster"
TAKT_MS = 200
HAKEN_AN = "☑"
HAKEN_AUS = "☐"
GRUPPEN_ZEILE = "gruppe:"

#: Die Spalten der Liste mit ihren Textschluesseln (feste Namen: Ein zusammengesetzter Schluessel liesse sich
#: weder suchen noch pruefen).
SPALTEN_TEXTE = {
    "name": "updates.col_name",
    "lokal": "updates.col_lokal",
    "neu": "updates.col_neu",
    "status": "updates.col_status",
}

#: Status -> Textschluessel. ``aktuell`` mit geholter Datei hat einen eigenen (``updates.status_geholt``).
STATUS_TEXTE = {
    wu.STATUS_NICHT_GEPRUEFT: "updates.status_nicht_geprueft",
    wu.STATUS_NEU: "updates.status_neu",
    wu.STATUS_NEU_HINWEIS: "updates.status_neu_hinweis",
    wu.STATUS_AKTUELL: "updates.status_aktuell",
    wu.STATUS_NEUER: "updates.status_neuer",
    wu.STATUS_UNKLAR: "updates.status_unklar",
    wu.STATUS_FEHLER: "updates.status_fehler",
    wu.STATUS_OHNE_QUELLE: "updates.status_ohne_quelle",
}
#: Meldung eines Befunds -> Textschluessel.
MELDUNG_TEXTE = {
    wu.MELDUNG_NETZ: "updates.meldung_netz",
    wu.MELDUNG_LIMIT: "updates.meldung_limit",
    wu.MELDUNG_NICHT_GEFUNDEN: "updates.meldung_nicht_gefunden",
    wu.MELDUNG_ANTWORT: "updates.meldung_antwort",
    wu.MELDUNG_ABGEBROCHEN: "updates.meldung_abgebrochen",
    wu.MELDUNG_KEINE_FREIGABE: "updates.meldung_keine_freigabe",
    wu.MELDUNG_KEINE_DATEI: "updates.meldung_keine_datei",
    wu.MELDUNG_LOKAL_UNLESBAR: "updates.meldung_lokal_unlesbar",
    wu.MELDUNG_FASSUNG_UNKLAR: "updates.meldung_fassung_unklar",
}
GRUPPEN_TEXTE = {
    wu.GRUPPE_PAYLOAD: "updates.gruppe_payload",
    wu.GRUPPE_WEBKIT: "updates.gruppe_webkit",
    wu.GRUPPE_EMU: "updates.gruppe_emu",
    wu.GRUPPE_WERKZEUG: "updates.gruppe_werkzeug",
    wu.GRUPPE_EIGEN: "updates.gruppe_eigen",
}


def groesse_text(n: int) -> str:
    """``24,5 MB`` - fuer die Knopfbeschriftung (das Programm hat dafuer ``_fmt_bytes``, das Fenster darf ohne)."""
    n = max(0, int(n))
    for einheit, schritt in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= schritt:
            return ("%.1f %s" % (n / schritt, einheit)).replace(".", ",")
    return "%d B" % n


def vorlaeufig(werkzeuge, bestand: wu.Bestand) -> list[wu.Befund]:
    """Die Liste vor der ersten Pruefung: was lokal vorliegt, ohne Urteil. Ohne Netz."""
    erg: list[wu.Befund] = []
    for w in werkzeuge:
        lokal = wu.lokale_fassung(w, bestand)
        if w.art == wu.ART_KEINE or not w.quelle:
            erg.append(wu.beurteilen(w, lokal, None))
        else:
            erg.append(wu.Befund(werkzeug=w, status=wu.STATUS_NICHT_GEPRUEFT, lokal=lokal.fassung,
                                 geholt=lokal.geholt, seite=w.seite or wu.seite_der_quelle(w.quelle)))
    return erg


class _Postfach:
    """Was die Arbeitsfaeden dem Fenster hinterlassen - ohne das Fenster zu kennen.

    Die Faeden halten nur dieses Postfach, nie das Fenster. Faellt der letzte Verweis auf ein Fenster in einem
    Arbeitsfaden, loest dort ``tk.Variable.__del__`` (und ``Image.__del__``) einen Tcl-Aufruf aus einem fremden
    Faden aus: „main thread is not in main loop“. Das Postfach traegt auch den Abbruch, damit ihn ein Faden
    setzen und lesen kann, ohne an das Fenster zu kommen.
    """

    def __init__(self) -> None:
        self.sperre = threading.Lock()
        self.z: dict = {"zeilen": [], "pruefe": None, "hole": None, "befunde": None, "fertig": None}
        self.abbruch = threading.Event()

    def melden(self, art: str, **werte) -> None:
        """Aus dem Arbeitsfaden: nur vormerken, der Takt des Fensters zeigt es an (unuebersetzt)."""
        with self.sperre:
            if art == "pruefe":
                self.z["pruefe"] = (int(werte.get("fertig", 0)), int(werte.get("gesamt", 0)))
            elif art == "hole":
                self.z["hole"] = (str(werte.get("name", "")), str(werte.get("text", "")),
                                  int(werte.get("fertig", 0)), int(werte.get("gesamt", 0)))
            elif art == "abgelegt":
                self.z["zeilen"].append(("updates.log_abgelegt", {"pfad": str(werte.get("text", ""))}))
            elif art == "fehler":
                self.z["zeilen"].append(("updates.log_fehler", {"name": str(werte.get("name", "")),
                                                                  "grund": str(werte.get("text", ""))}))
            elif art == "ohne_summe":
                self.z["zeilen"].append(("updates.log_ohne_summe", {"datei": str(werte.get("text", ""))}))

    def abliefern(self, art: str, befunde=None, ergebnis=None) -> None:
        with self.sperre:
            if befunde is not None or art == "pruefen":
                self.z["befunde"] = befunde
            self.z["fertig"] = (art, ergebnis)


def _pruefen_arbeit(post: _Postfach, netz, basis: str, mitgeliefert_finden, ampr: list, ampr_ordner: str) -> None:
    """Der Arbeitsfaden der Pruefung. Fasst kein Tk an, uebersetzt nichts, kennt das Fenster nicht."""
    befunde = None
    try:
        bestand = wu.bestand_lesen(mitgeliefert_finden, basis)
        speicher = wu.speicher_lesen(basis)
        befunde, neuer = wu.pruefen(wu.WERKZEUGE, bestand, netz, speicher, melden=post.melden, abbruch=post.abbruch,
                                    ampr_vorhanden=lambda: ampr, ampr_ordner=ampr_ordner)
        wu.speicher_schreiben(basis, neuer)
    except Exception:  # noqa: BLE001
        logger.exception("Pruefung der Werkzeug-Updates")
    finally:
        post.abliefern("pruefen", befunde)


def _holen_arbeit(post: _Postfach, netz, basis: str, wahl: list, ampr_ordner: str) -> None:
    """Der Arbeitsfaden des Holens. Fasst kein Tk an, uebersetzt nichts, kennt das Fenster nicht."""
    ergebnis = wu.Ergebnis()
    try:
        ergebnis = wu.holen([b for b in wahl if b.teile], basis, netz, post.melden, post.abbruch)
        for b in [b for b in wahl if b.ampr]:
            if post.abbruch.is_set():
                ergebnis.abgebrochen = True
                break
            abgelegt, fehler = wu.holen_emu(b, ampr_ordner, netz)
            ergebnis.abgelegt.extend(abgelegt)
            ergebnis.fehler.extend("%s: %s" % (b.werkzeug.name, f) for f in fehler)
            with post.sperre:
                if abgelegt:
                    post.z["zeilen"].append(("updates.log_ampr", {"anzahl": len(abgelegt), "ordner": ampr_ordner}))
                for f in fehler:
                    post.z["zeilen"].append(("updates.log_fehler", {"name": b.werkzeug.name, "grund": f}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Holen der Werkzeug-Updates")
        ergebnis.fehler.append(str(exc))
    finally:
        post.abliefern("holen", None, ergebnis)


class UpdatesFenster:
    """Das Fenster. Eine Instanz je geoeffnetem Fenster."""

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int], netz=None,
                 automatisch: bool = True) -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.netz = netz if netz is not None else wu.Netz()
        self.basis = gui._updates_basis()
        self.befunde: list[wu.Befund] = []
        self.gewaehlt: set[str] = set()
        self._post = _Postfach()
        self._abbruch = self._post.abbruch
        self._arbeit: "threading.Thread | None" = None
        self._schliesst = False
        self._takt_id = None
        self._bauen()
        self._liste_neu(self._vorlaeufig())
        self._takt()
        if automatisch:
            self.pruefen_starten()

    # ------------------------------------------------------------------
    # Hilfen
    # ------------------------------------------------------------------
    def _status(self, text: str) -> None:
        try:
            self.status_zeile.configure(text=text)
        except tk.TclError:
            pass

    def status_text(self) -> str:
        """Der Text der Statuszeile (fuer Tests und Diagnose)."""
        try:
            return str(self.status_zeile.cget("text"))
        except tk.TclError:
            return ""

    def _protokoll(self, text: str) -> None:
        try:
            self.protokoll.configure(state="normal")
            self.protokoll.insert("end", text + "\n")
            self.protokoll.see("end")
            self.protokoll.configure(state="disabled")
        except tk.TclError:
            pass

    def _bestand(self) -> wu.Bestand:
        return wu.bestand_lesen(self.g._mitgeliefert_finden, self.basis)

    def _vorlaeufig(self) -> list[wu.Befund]:
        return vorlaeufig(wu.WERKZEUGE, self._bestand())

    def _laeuft(self) -> bool:
        return self._arbeit is not None and self._arbeit.is_alive()

    def _beschaeftigt(self) -> bool:
        """Laeuft ein Faden - oder wartet sein Ergebnis noch darauf, vom Takt uebernommen zu werden?

        Zwischen dem Ende des Fadens und dem naechsten Takt (200 ms) laeuft nichts mehr, das Ergebnis ist aber noch
        nicht in der Liste: Ein neuer Start in dieser Luecke vermischte die Ergebnisse beider Laeufe.
        """
        return self._laeuft() or self._post.z["fertig"] is not None

    def _ablage(self) -> str:
        return wu.update_ordner(self.basis)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _karte(self, eltern, titel_schluessel: str, polster=(16, 12)):
        """Eine runde Karte mit Ueberschrift (``pw.Karte``: nichts davon bleibt im Hauptprogramm stehen)."""
        karte = self.g._pw.Karte(eltern, bg=self.c["bg_card"], padx=polster[0], pady=polster[1])
        tk.Label(karte, text=self.t(titel_schluessel).upper(), font=(self.F, self.pt(10), "bold"),
                 bg=self.c["bg_card"], fg=self.c["fg_primary"], anchor="w").pack(fill="x", pady=(0, 8))
        return karte

    def _pille(self, eltern, schluessel: str, befehl, akzent: bool = False):
        optionen = {"style": "Accent.TButton"} if akzent else {}
        return self.g._pw.Button(eltern, text=self.t(schluessel), command=befehl, **optionen)

    def _bauen(self) -> None:
        g, t, c, F, pt = self.g, self.t, self.c, self.F, self.pt
        pw = g._pw
        self.win = g._build_modern_toplevel(t("updates.window_title"), 1180, 900, min_width=900, min_height=640)
        self.win.configure(bg=c["bg_main"])

        # Statuszeile, Balken und Knopfleiste unten zuerst packen (von unten nach oben) - sonst quetscht sie die
        # Mindesthoehe weg. Die Statuszeile ist ein Label ohne ``tk.StringVar``: Eine Variable, die der Muellsammler
        # in einem Arbeitsfaden einsammelt, ruft dort Tcl auf.
        status = tk.Frame(self.win, bg=c["bg_main"], padx=14, pady=5)
        status.pack(side="bottom", fill="x")
        self.status_zeile = tk.Label(status, text=t("updates.status_bereit"), font=(F, pt(9)), bg=c["bg_main"],
                                     fg=c["fg_secondary"], anchor="w")
        self.status_zeile.pack(side="left")
        self.balken = pw.Progressbar(self.win, mode="determinate", maximum=100.0)
        self.balken.pack(side="bottom", fill="x", padx=14, pady=(0, 2))
        leiste = tk.Frame(self.win, bg=c["bg_main"], padx=14, pady=8)
        leiste.pack(side="bottom", fill="x")

        self.pruefen_knopf = self._pille(leiste, "updates.pruefen", self.pruefen_starten, akzent=True)
        self.pruefen_knopf.pack(side="left")
        self.alle_knopf = self._pille(leiste, "updates.alle_neuen", self._alle_neuen)
        self.alle_knopf.pack(side="left", padx=(10, 0))
        self.keine_knopf = self._pille(leiste, "updates.auswahl_aufheben", self._auswahl_aufheben)
        self.keine_knopf.pack(side="left", padx=(10, 0))
        self.holen_knopf = self._pille(leiste, "updates.holen", self._herunterladen, akzent=True)
        self.holen_knopf.pack(side="left", padx=(10, 0))
        self.abbrechen_knopf = self._pille(leiste, "action.cancel", self._abbrechen)
        self.abbrechen_knopf.pack(side="left", padx=(10, 0))
        self._pille(leiste, "action.close", self._schliessen).pack(side="right")

        rumpf = tk.Frame(self.win, bg=c["bg_main"], padx=14)
        rumpf.pack(fill="both", expand=True)
        rumpf.columnconfigure(0, weight=1)
        rumpf.rowconfigure(1, weight=1)
        kopf = tk.Frame(rumpf, bg=c["bg_main"])
        kopf.grid(row=0, column=0, sticky="ew", pady=(10, 8))
        tk.Label(kopf, text=t("updates.page_title"), font=(F, pt(20), "bold"), bg=c["bg_main"], fg=c["fg_primary"],
                 anchor="w").pack(fill="x")
        tk.Label(kopf, text=t("updates.page_subtitle"), font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_secondary"],
                 anchor="w", justify="left", wraplength=1000).pack(fill="x")

        # Die Liste
        rahmen = tk.Frame(rumpf, bg=c["bg_main"])
        rahmen.grid(row=1, column=0, sticky="nsew")
        spalten = ("auswahl", "name", "lokal", "neu", "status")
        self.liste = pw.Treeview(rahmen, columns=spalten, show="headings", selectmode="browse")
        self.liste.heading("auswahl", text="", anchor="center")
        self.liste.column("auswahl", width=44, minwidth=44, stretch=False, anchor="center")
        for spalte, breite, dehnen in (("name", 330, False), ("lokal", 150, False), ("neu", 150, False),
                                       ("status", 300, True)):
            self.liste.heading(spalte, text=t(SPALTEN_TEXTE[spalte]), anchor="w")
            self.liste.column(spalte, width=breite, anchor="w", stretch=dehnen)
        rolle = pw.Scrollbar(rahmen, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=rolle.set)
        self.liste.pack(side="left", fill="both", expand=True)
        rolle.pack(side="right", fill="y")
        self.liste.tag_configure("neu", foreground=c["fg_accent"])
        self.liste.tag_configure("warn", foreground=c["fg_warning"])
        self.liste.tag_configure("still", foreground=c["fg_secondary"])
        self.liste.tag_configure("gruppe", foreground=c["fg_accent"], font=(F, pt(9), "bold"))
        self.liste.bind("<<TreeviewSelect>>", self._zeile_gewaehlt)
        self.liste.bind("<Button-1>", self._klick, add="+")
        self.liste.bind("<space>", self._leertaste)

        # Einzelheiten und Protokoll nebeneinander
        unten = tk.Frame(rumpf, bg=c["bg_main"])
        unten.grid(row=2, column=0, sticky="ew", pady=(10, 4))
        unten.columnconfigure(0, weight=3, uniform="unten")
        unten.columnconfigure(1, weight=2, uniform="unten")
        details = self._karte(unten, "updates.karte_details")
        details.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        # Die beiden Knoepfe der Einzelheiten zuerst unten packen - sonst quetscht sie das Textfeld weg.
        knoepfe = tk.Frame(details, bg=c["bg_card"])
        knoepfe.pack(side="bottom", fill="x", pady=(8, 0))
        self.seite_knopf = self._pille(knoepfe, "updates.seite", self._seite_oeffnen)
        self.seite_knopf.pack(side="left")
        self._pille(knoepfe, "updates.ordner", self._ordner_oeffnen).pack(side="left", padx=(8, 0))
        # ``width`` klein: Ein Textfeld ohne Breite will 80 Zeichen und treibt zwei nebeneinander auf ~1800 Punkte;
        # die Breite verteilt das Gitter (3 : 2).
        self.details = pw.Text(details, width=10, height=5, font=(F, pt(9)), bg=c["console_bg"], fg=c["console_fg"],
                               relief="flat", wrap="word", state="disabled")
        self.details.pack(fill="both", expand=True)
        protokoll = self._karte(unten, "updates.karte_protokoll")
        protokoll.grid(row=0, column=1, sticky="nsew")
        self.protokoll = pw.Text(protokoll, width=10, height=5, font=(self.M, pt(9)), bg=c["console_bg"],
                                 fg=c["console_fg"], relief="flat", wrap="word", state="disabled")
        self.protokoll.pack(fill="both", expand=True)

        self.win.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.win.bind("<Destroy>", self._bei_zerstoerung, add="+")
        self._details_zeigen("")
        self._knoepfe_pruefen()

    # ------------------------------------------------------------------
    # Die Liste
    # ------------------------------------------------------------------
    def _status_text(self, b: wu.Befund) -> str:
        schluessel = STATUS_TEXTE.get(b.status, "updates.status_unklar")
        if b.status == wu.STATUS_AKTUELL and b.geholt:
            schluessel = "updates.status_aktuell_geholt"
        text = self.t(schluessel)
        if b.stand and b.status != wu.STATUS_NICHT_GEPRUEFT:
            text = self.t("updates.status_mit_stand", status=text, datum=b.stand)
        return text

    @staticmethod
    def _marke(b: wu.Befund) -> str:
        if b.status in (wu.STATUS_NEU, wu.STATUS_NEU_HINWEIS):
            return "neu"
        if b.status in (wu.STATUS_FEHLER, wu.STATUS_UNKLAR):
            return "warn"
        return "still"

    def _liste_neu(self, befunde: list[wu.Befund]) -> None:
        """Zeigt die Befunde; Auswahl und Haken bleiben, soweit es die Zeile noch gibt."""
        self.befunde = list(befunde)
        gewaehlte_zeile = ""
        try:
            auswahl = self.liste.selection()
            gewaehlte_zeile = auswahl[0] if auswahl else ""
            self.liste.delete(*self.liste.get_children())
        except tk.TclError:
            return
        ladbar = {b.werkzeug.schluessel for b in self.befunde if b.ladbar}
        self.gewaehlt &= ladbar
        letzte = None
        for b in self.befunde:
            w = b.werkzeug
            if w.gruppe != letzte:
                letzte = w.gruppe
                self.liste.insert("", "end", iid=GRUPPEN_ZEILE + w.gruppe,
                                  values=("", self.t(GRUPPEN_TEXTE.get(w.gruppe, "updates.gruppe_payload")), "", "", ""),
                                  tags=("gruppe",))
            haken = (HAKEN_AN if w.schluessel in self.gewaehlt else HAKEN_AUS) if b.ladbar else ""
            self.liste.insert("", "end", iid=w.schluessel,
                              values=(haken, w.name, b.lokal or "–", b.neu or "–", self._status_text(b)),
                              tags=(self._marke(b),))
        if gewaehlte_zeile and self.liste.exists(gewaehlte_zeile):
            self.liste.selection_set(gewaehlte_zeile)
        self._details_zeigen(self._aktuelle_zeile())
        self._knoepfe_pruefen()

    def _aktuelle_zeile(self) -> str:
        try:
            auswahl = self.liste.selection()
        except tk.TclError:
            return ""
        return auswahl[0] if auswahl and not auswahl[0].startswith(GRUPPEN_ZEILE) else ""

    def _befund(self, schluessel: str) -> "wu.Befund | None":
        for b in self.befunde:
            if b.werkzeug.schluessel == schluessel:
                return b
        return None

    def _haken_setzen(self, schluessel: str) -> None:
        b = self._befund(schluessel)
        if b is None:
            return
        try:
            self.liste.set(schluessel, "auswahl", (HAKEN_AN if schluessel in self.gewaehlt else HAKEN_AUS)
                           if b.ladbar else "")
        except tk.TclError:
            pass

    def _umschalten(self, schluessel: str) -> None:
        b = self._befund(schluessel)
        if b is None or not b.ladbar or self._laeuft():
            return
        if schluessel in self.gewaehlt:
            self.gewaehlt.discard(schluessel)
        else:
            self.gewaehlt.add(schluessel)
        self._haken_setzen(schluessel)
        self._knoepfe_pruefen()

    def _klick(self, ereignis) -> None:
        try:
            if self.liste.identify_region(ereignis.x, ereignis.y) != "cell":
                return
            if self.liste.identify_column(ereignis.x) != "#1":
                return
            zeile = self.liste.identify_row(ereignis.y)
        except tk.TclError:
            return
        if zeile and not zeile.startswith(GRUPPEN_ZEILE):
            self._umschalten(zeile)

    def _leertaste(self, _ereignis=None) -> str:
        zeile = self._aktuelle_zeile()
        if zeile:
            self._umschalten(zeile)
        return "break"

    def _alle_neuen(self) -> None:
        if self._laeuft():
            return
        self.gewaehlt = {b.werkzeug.schluessel for b in self.befunde if b.ladbar}
        for b in self.befunde:
            self._haken_setzen(b.werkzeug.schluessel)
        self._knoepfe_pruefen()

    def _auswahl_aufheben(self) -> None:
        if self._laeuft():
            return
        alt, self.gewaehlt = self.gewaehlt, set()
        for schluessel in alt:
            self._haken_setzen(schluessel)
        self._knoepfe_pruefen()

    def _zeile_gewaehlt(self, _ereignis=None) -> None:
        self._details_zeigen(self._aktuelle_zeile())
        self._knoepfe_pruefen()

    def _zeit_text(self, sekunden: int) -> str:
        try:
            return time.strftime("%H:%M", time.localtime(int(sekunden)))
        except (OverflowError, OSError, ValueError):
            return ""

    def _meldung_text(self, b: wu.Befund) -> str:
        schluessel = MELDUNG_TEXTE.get(b.meldung, "")
        if not schluessel:
            return ""
        if b.meldung == wu.MELDUNG_LIMIT and b.detail.isdigit():
            zeit = self._zeit_text(int(b.detail))
            if zeit:
                return self.t("updates.meldung_limit_bis", zeit=zeit)
        text = self.t(schluessel)
        if b.meldung == wu.MELDUNG_NETZ and b.detail:
            text += " " + b.detail
        return text

    def _details_zeigen(self, schluessel: str) -> None:
        t = self.t
        b = self._befund(schluessel) if schluessel else None
        if b is None:
            zeilen = [t("updates.detail_leer")]
        else:
            w = b.werkzeug
            zeilen = [w.name]
            if b.lokal:
                zeilen.append(t("updates.detail_lokal_geholt" if b.geholt else "updates.detail_lokal",
                                fassung=b.lokal))
            if b.neu:
                zeilen.append(t("updates.detail_neu", fassung=b.neu, datum=b.datum) if b.datum
                              else t("updates.detail_neu_ohne_datum", fassung=b.neu))
                if b.vorab:
                    zeilen.append(t("updates.detail_vorab"))
            if b.teile:
                zeilen.append(t("updates.detail_dateien", liste=", ".join(
                    "%s (%s)" % (teil.ziel, groesse_text(teil.groesse)) if teil.groesse else teil.ziel
                    for teil in b.teile)))
            elif b.ampr:
                zeilen.append(t("updates.detail_dateien", liste=", ".join(
                    "%s %s" % (a.fassung, a.variante) for a in b.ampr)))
            meldung = self._meldung_text(b)
            if meldung:
                zeilen.append(meldung)
            if w.hinweis:
                zeilen.append(t(w.hinweis))
        try:
            self.details.configure(state="normal")
            self.details.delete("1.0", "end")
            self.details.insert("end", "\n".join(zeilen))
            self.details.configure(state="disabled")
        except tk.TclError:
            pass

    def _knoepfe_pruefen(self) -> None:
        laeuft = self._beschaeftigt()
        ladbare = [b for b in self.befunde if b.ladbar]
        wahl = [b for b in ladbare if b.werkzeug.schluessel in self.gewaehlt]
        zeile = self._aktuelle_zeile()
        b = self._befund(zeile) if zeile else None
        try:
            self.pruefen_knopf.configure(state="disabled" if laeuft else "normal")
            self.alle_knopf.configure(state="normal" if ladbare and not laeuft else "disabled")
            self.keine_knopf.configure(state="normal" if wahl and not laeuft else "disabled")
            self.holen_knopf.configure(
                state="normal" if wahl and not laeuft else "disabled",
                text=(self.t("updates.holen_n", anzahl=len(wahl), groesse=groesse_text(sum(x.groesse for x in wahl)))
                      if wahl else self.t("updates.holen")))
            self.abbrechen_knopf.configure(state="normal" if laeuft else "disabled")
            self.seite_knopf.configure(state="normal" if b is not None and b.seite else "disabled")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Pruefen
    # ------------------------------------------------------------------
    def pruefen_starten(self) -> None:
        """Fragt jede Quelle nach ihrer neuesten Freigabe - im Arbeitsfaden."""
        if self._beschaeftigt() or self._schliesst:
            return
        self._abbruch.clear()
        self.gewaehlt = set()
        ampr = self.g._updates_ampr_vorhanden()
        ampr_ordner = self.g._updates_ampr_ordner()
        self._protokoll(self.t("updates.log_pruefung", anzahl=len(wu.WERKZEUGE)))
        self._status(self.t("updates.status_pruefe", fertig=0, gesamt=len(wu.quellen(wu.WERKZEUGE))))
        self.balken["value"] = 0
        # Der Faden bekommt nur, was er braucht - nie ``self`` (siehe _Postfach).
        self._arbeit = threading.Thread(
            target=_pruefen_arbeit, daemon=True, name="werkzeug_updates",
            args=(self._post, self.netz, self.basis, self.g._mitgeliefert_finden, ampr, ampr_ordner))
        self._arbeit.start()
        self._knoepfe_pruefen()

    # ------------------------------------------------------------------
    # Holen
    # ------------------------------------------------------------------
    def _herunterladen(self) -> None:
        if self._beschaeftigt() or self._schliesst:
            return
        wahl = [b for b in self.befunde if b.ladbar and b.werkzeug.schluessel in self.gewaehlt]
        if not wahl:
            return
        self._abbruch.clear()
        ampr_ordner = self.g._updates_ampr_ordner()
        for b in wahl:
            self._protokoll(self.t("updates.log_hole", name=b.werkzeug.name))
        self.balken["value"] = 0
        self._arbeit = threading.Thread(target=_holen_arbeit, daemon=True, name="werkzeug_updates_holen",
                                        args=(self._post, self.netz, self.basis, wahl, ampr_ordner))
        self._arbeit.start()
        self._knoepfe_pruefen()

    def _nach_dem_holen(self, ergebnis: wu.Ergebnis) -> None:
        """Urteilt noch einmal ueber alles - der Bestand hat sich geaendert, die Freigaben nicht."""
        bestand = self._bestand()
        speicher = wu.speicher_lesen(self.basis)
        ampr = self.g._updates_ampr_vorhanden()
        ampr_ordner = self.g._updates_ampr_ordner()
        self._liste_neu([wu.neu_beurteilen(b, bestand, speicher, ampr, ampr_ordner) for b in self.befunde])
        if ergebnis.abgelegt:
            self._protokoll(self.t("updates.log_ablage", ordner=self._ablage()))
            hook = getattr(self.g, "_updates_geholt", None)
            if hook is not None:
                try:
                    hook()
                except Exception:  # noqa: BLE001
                    logger.exception("Rueckruf nach dem Holen")

    # ------------------------------------------------------------------
    # Knoepfe
    # ------------------------------------------------------------------
    def _abbrechen(self) -> None:
        if self._laeuft():
            self._abbruch.set()
            self._status(self.t("updates.status_abbruch"))

    def _ordner_oeffnen(self) -> None:
        ordner = self._ablage()
        try:
            os.makedirs(ordner, exist_ok=True)
        except OSError as exc:
            logger.debug("Update-Ordner nicht anlegbar: %s", exc)
            self._protokoll(self.t("updates.log_ordner_fehler", ordner=ordner))
            return
        if not plattform.datei_oeffnen(ordner):
            self._protokoll(self.t("updates.log_ordner_fehler", ordner=ordner))

    def _seite_oeffnen(self) -> None:
        b = self._befund(self._aktuelle_zeile())
        if b is not None and b.seite and not webbrowser.open(b.seite):
            self._protokoll(self.t("updates.log_seite_fehler", adresse=b.seite))

    # ------------------------------------------------------------------
    # Takt
    # ------------------------------------------------------------------
    def _takt(self) -> None:
        if self._schliesst:
            return
        try:
            self._takt_arbeiten()
        except tk.TclError:
            return
        except Exception:  # noqa: BLE001
            logger.exception("Takt des Updates-Fensters")
        try:
            self._takt_id = self.win.after(TAKT_MS, self._takt)
        except tk.TclError:
            self._takt_id = None

    def _takt_arbeiten(self) -> None:
        post = self._post
        with post.sperre:
            zeilen, post.z["zeilen"] = post.z["zeilen"], []
            pruefe, post.z["pruefe"] = post.z["pruefe"], None
            hole, post.z["hole"] = post.z["hole"], None
            befunde, post.z["befunde"] = post.z["befunde"], None
            fertig, post.z["fertig"] = post.z["fertig"], None
        for schluessel, werte in zeilen:
            self._protokoll(self.t(schluessel, **werte))
        if pruefe is not None and pruefe[1]:
            self.balken["value"] = 100.0 * pruefe[0] / pruefe[1]
            self._status(self.t("updates.status_pruefe", fertig=pruefe[0], gesamt=pruefe[1]))
        if hole is not None:
            name, datei, gelesen, gesamt = hole
            prozent = int(100.0 * gelesen / gesamt) if gesamt else 0
            self.balken["value"] = prozent
            self._status(self.t("updates.status_hole", name=name, datei=datei, prozent=prozent))
        if befunde is not None:
            self._liste_neu(befunde)
        if fertig is None:
            return
        art, ergebnis = fertig
        self._arbeit = None
        self.balken["value"] = 0
        if art == "pruefen":
            zaehler = wu.zusammenfassung(self.befunde)
            if befunde is None:
                self._status(self.t("updates.status_fehlgeschlagen"))
            elif self._abbruch.is_set():
                self._status(self.t("updates.status_abgebrochen"))
            else:
                self._status(self.t(
                    "updates.status_geprueft", neu=zaehler.get(wu.STATUS_NEU, 0),
                    hinweis=zaehler.get(wu.STATUS_NEU_HINWEIS, 0),
                    aktuell=zaehler.get(wu.STATUS_AKTUELL, 0) + zaehler.get(wu.STATUS_NEUER, 0),
                    fehler=zaehler.get(wu.STATUS_FEHLER, 0)))
        else:
            self._nach_dem_holen(ergebnis)
            if self._abbruch.is_set() or ergebnis.abgebrochen:
                self._status(self.t("updates.status_abgebrochen"))
            elif ergebnis.fehler:
                self._status(self.t("updates.status_geholt_fehler", anzahl=len(ergebnis.abgelegt),
                                    fehler=len(ergebnis.fehler)))
            else:
                self._status(self.t("updates.status_geholt", anzahl=len(ergebnis.abgelegt)))
        self._knoepfe_pruefen()

    # ------------------------------------------------------------------
    # Schliessen
    # ------------------------------------------------------------------
    def _schliessen(self) -> None:
        if self._laeuft():
            if not messagebox.askyesno(self.t("updates.window_title"), self.t("updates.close_running"),
                                       parent=self.win):
                return
            self._abbruch.set()
        self.win.destroy()

    def _bei_zerstoerung(self, ereignis) -> None:
        if ereignis.widget is not self.win:
            return
        self._schliesst = True
        self._abbruch.set()
        if self._takt_id is not None:
            try:
                self.win.after_cancel(self._takt_id)
            except tk.TclError:
                pass
        if getattr(self.g, FENSTER_ATTRIBUT, None) is self:
            setattr(self.g, FENSTER_ATTRIBUT, None)


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int], netz=None,
            automatisch: bool = True) -> UpdatesFenster:
    """Oeffnet das Fenster - oder holt das offene nach vorn.

    Args:
        netz: Nur fuer Tests - ersetzt :class:`werkzeug_updates.Netz`.
        automatisch: ``False`` oeffnet, ohne zu pruefen (Tests, die den Zustand vor der Pruefung sehen wollen).
    """
    vorhanden = getattr(gui, FENSTER_ATTRIBUT, None)
    if vorhanden is not None:
        try:
            if vorhanden.win.winfo_exists():
                vorhanden.win.deiconify()
                vorhanden.win.lift()
                return vorhanden
        except tk.TclError:
            pass
    fenster = UpdatesFenster(gui, schrift, mono, pt, netz=netz, automatisch=automatisch)
    setattr(gui, FENSTER_ATTRIBUT, fenster)
    return fenster
