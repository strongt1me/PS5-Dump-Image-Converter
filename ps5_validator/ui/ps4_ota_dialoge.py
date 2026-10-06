# -*- coding: utf-8 -*-
"""Die kleinen Dialoge von „PS4 PKG -> OTA“: Entpacken, Zusammenfuehren, Neupacken, Bauen, Vorschau.

Jeder Dialog hat zwei Teile, damit er sich ohne echtes Fenster pruefen laesst
(``conftest.py`` sperrt modale Fenster - ein ``wait_window`` im Test haelt den
Lauf an):

* ``baue_*`` baut das Fenster und liefert ``(fenster, antwort)``. ``antwort`` ist
  ein dict, das **leer** bleibt, solange der Anwender nicht „OK“ drueckt, und
  danach seine Eingaben traegt. Der Test setzt die Felder und ruft den
  Knopf auf.
* ``frage_*`` ruft ``baue_*``, wartet auf das Fenster und gibt die Antwort
  zurueck (``None`` bei Abbruch). Nur die Oberflaeche ruft diese.

Die Texte kommen ueber ``gui._t`` herein; dieses Modul bindet ``i18n`` nicht ein.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from ps5_validator.ui import ps4_ota_bausteine as bs
from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import ps4pkg_bibliothek as bib

#: Die Auswahl der PFSC-Kompression im Werkzeug.
PFSC_MODI = ("compressed", "store")


class _Rahmen:
    """Gemeinsamer Grundbau: Fenster, Koerper, Knopfreihe, Hilfen fuer Zeilen.

    Alles darin ist rund wie im Hauptprogramm (Pillenform): Knoepfe, Felder,
    Klapplisten, Ankreuzfelder - gebaut von :class:`ps4_ota_bausteine.Look`.
    """

    def __init__(self, gui, eltern, titel: str, breite: int, hoehe: int, schrift: str, pt: Callable[[int], int]) -> None:
        self.g = gui
        self.c = gui._COLORS
        self.F = schrift
        self.pt = pt
        self.look = bs.Look.gemeinsam(gui, schrift, schrift, pt)
        self.win = gui._build_modern_toplevel(titel, breite, hoehe, min_width=breite - 60,
                                              min_height=hoehe - 40, parent=eltern)
        try:
            self.win.transient(eltern)
        except tk.TclError:
            pass
        self.antwort: dict = {}
        self.knopfreihe = tk.Frame(self.win, bg=self.c["bg_main"], padx=16, pady=12)
        self.knopfreihe.pack(side="bottom", fill="x")
        self.koerper = tk.Frame(self.win, bg=self.c["bg_main"], padx=18)
        self.koerper.pack(fill="both", expand=True)

    def kopf(self, titel: str, untertitel: str = "") -> None:
        kopf = self.g._build_modern_header(self.win, titel, untertitel or None)
        # Der Kopf entsteht erst nach dem Koerper und stuende sonst darunter (pack ordnet nach Reihenfolge).
        kopf.pack_configure(before=self.koerper)
        self.kopf_rahmen = kopf

    def _reihe(self, beschriftung: str, breite: int) -> tk.Frame:
        """Eine Zeile mit Beschriftung links; was rechts davon steht, packt der Aufrufer dazu."""
        reihe = tk.Frame(self.koerper, bg=self.c["bg_main"])
        reihe.pack(fill="x", pady=4)
        self.look.beschriftung(reihe, beschriftung, width=breite).pack(side="left")
        return reihe

    #: Breite der Beschriftungen links in Zeichen - so, dass auch "Rechenkerne (0 = alle)" hineinpasst.
    BESCHRIFTUNG_BREITE = 24

    def zeile_pfad(self, beschriftung: str, var: tk.StringVar, waehlen: "Callable[[], None] | None" = None,
                   breite: int = BESCHRIFTUNG_BREITE) -> tk.Entry:
        reihe = self._reihe(beschriftung, breite)
        feld = self.look.eingabe(reihe, var, 20)
        feld.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if waehlen is not None:
            self.look.knopf(reihe, "…", waehlen, hoehe=30).pack(side="left")
        return feld.eingabe

    def zeile_wert(self, beschriftung: str, var, breite: int = BESCHRIFTUNG_BREITE, eingabebreite: int = 10) -> tk.Entry:
        reihe = self._reihe(beschriftung, breite)
        feld = self.look.eingabe(reihe, var, eingabebreite)
        feld.pack(side="left")
        return feld.eingabe

    def zeile_auswahl(self, beschriftung: str, var: tk.StringVar, werte, breite: int = BESCHRIFTUNG_BREITE, befehl=None):
        """Eine Klappliste als Pille mit Beschriftung davor."""
        reihe = self._reihe(beschriftung, breite)
        box = self.look.auswahl(reihe, var, list(werte), befehl=befehl)
        box.pack(side="left")
        return box

    def haken(self, text: str, var: tk.BooleanVar, warnung: bool = False):
        kasten = self.look.haken(self.koerper, text, var, farbe="fg_warning" if warnung else "fg_primary")
        kasten.pack(anchor="w", pady=3)
        return kasten

    def hinweis(self, text: str, farbe: "str | None" = None) -> tk.Label:
        beschriftung = self.look.hinweis(self.koerper, text, farbe)
        beschriftung.pack(fill="x", pady=(6, 2))
        return beschriftung

    def knoepfe(self, ok_text: str, ok_befehl: Callable[[], None], abbruch_text: str):
        self.look.knopf(self.knopfreihe, abbruch_text, self.schliessen, hoehe=32).pack(side="right")
        ok = self.look.knopf(self.knopfreihe, ok_text, ok_befehl, akzent=True, hoehe=32)
        ok.pack(side="right", padx=(0, 8))
        self.win.bind("<Escape>", lambda e: self.schliessen())
        return ok

    def schliessen(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def warten(self) -> "dict | None":
        try:
            self.win.grab_set()
        except tk.TclError:
            pass
        self.win.wait_window(self.win)
        return self.antwort or None


def _ordner_waehlen(g, win, var: tk.StringVar, titel: str) -> None:
    gewaehlt = filedialog.askdirectory(title=titel, initialdir=var.get() or None, parent=win)
    if gewaehlt:
        var.set(os.path.normpath(gewaehlt))


# ---------------------------------------------------------------------------
# Entpacken
# ---------------------------------------------------------------------------

def baue_entpacken(gui, eltern, pakete: "list[bib.PkgEintrag]", vorgaben: dict, schrift: str,
                   pt: Callable[[int], int]) -> "tuple[_Rahmen, tk.Misc]":
    t = gui._t
    r = _Rahmen(gui, eltern, t("ps4ota.dlg_entpacken_titel"), 700, 430, schrift, pt)
    r.kopf(t("ps4ota.dlg_entpacken_titel"), t("ps4ota.dlg_entpacken_untertitel", anzahl=len(pakete)))
    ziel = tk.StringVar(value=vorgaben.get("ziel", ""))
    dump = tk.BooleanVar(value=bool(vorgaben.get("dump_form", True)))
    oeffnen = tk.BooleanVar(value=bool(vorgaben.get("oeffnen", False)))
    passcode = tk.StringVar(value=vorgaben.get("passcode", ""))
    r.zeile_pfad(t("ps4ota.dlg_ziel"), ziel, lambda: _ordner_waehlen(gui, r.win, ziel, t("ps4ota.dlg_ziel_waehlen")))
    r.haken(t("ps4ota.dlg_dump_form"), dump)
    r.haken(t("ps4ota.dlg_ordner_oeffnen"), oeffnen)
    r.hinweis(t("ps4ota.dlg_dump_form_hinweis"))
    r.zeile_wert(t("ps4ota.dlg_passcode"), passcode, eingabebreite=36)
    r.hinweis(t("ps4ota.dlg_passcode_hinweis"))

    def _ok() -> None:
        pfad = ziel.get().strip()
        if not pfad:
            messagebox.showwarning(t("ps4ota.dlg_entpacken_titel"), t("ps4ota.dlg_ziel_fehlt"), parent=r.win)
            return
        code = passcode.get().strip()
        if code and len(code) != 32:
            messagebox.showwarning(t("ps4ota.dlg_entpacken_titel"), t("ps4ota.dlg_passcode_laenge"), parent=r.win)
            return
        r.antwort.update(ziel=pfad, dump_form=dump.get(), oeffnen=oeffnen.get(), passcode=code or None)
        r.schliessen()

    ok = r.knoepfe(t("ps4ota.dlg_los"), _ok, t("ps4ota.dlg_abbrechen"))
    r.felder = {"ziel": ziel, "dump": dump, "oeffnen": oeffnen, "passcode": passcode}   # type: ignore[attr-defined]
    return r, ok


def frage_entpacken(gui, eltern, pakete, vorgaben, schrift, pt) -> "dict | None":
    r, _ok = baue_entpacken(gui, eltern, pakete, vorgaben, schrift, pt)
    return r.warten()


# ---------------------------------------------------------------------------
# Zusammenfuehren
# ---------------------------------------------------------------------------

def baue_zusammenfuehren(gui, eltern, basis: bib.PkgEintrag, update: bib.PkgEintrag, vorgaben: dict,
                         schrift: str, pt: Callable[[int], int]) -> "tuple[_Rahmen, tk.Misc]":
    t = gui._t
    r = _Rahmen(gui, eltern, t("ps4ota.dlg_zusammen_titel"), 740, 520, schrift, pt)
    r.kopf(t("ps4ota.dlg_zusammen_titel"), t("ps4ota.dlg_zusammen_untertitel"))
    tk.Label(r.koerper, justify="left", anchor="w", font=(schrift, pt(9)), bg=r.c["bg_main"], fg=r.c["fg_primary"],
             text=t("ps4ota.dlg_zusammen_paare", basis=basis.datei, basis_ver=basis.app_ver or "-",
                    update=update.datei, update_ver=update.app_ver or "-")).pack(fill="x", pady=(0, 6))
    standard_name = "%s [%s] [%s] merged.pkg" % (bib.dateiname_bereinigen(basis.titel or basis.title_id),
                                                  basis.title_id, bib.ohne_fuehrende_nullen(update.app_ver))
    ordner = tk.StringVar(value=vorgaben.get("ordner", basis.ordner))
    name = tk.StringVar(value=vorgaben.get("name", standard_name))
    pruefen = tk.BooleanVar(value=bool(vorgaben.get("pruefen", False)))
    modus = tk.StringVar(value=vorgaben.get("modus", "compressed"))
    arbeiter = tk.StringVar(value=str(vorgaben.get("arbeiter", 1)))
    r.zeile_pfad(t("ps4ota.dlg_ziel"), ordner, lambda: _ordner_waehlen(gui, r.win, ordner, t("ps4ota.dlg_ziel_waehlen")))
    r.zeile_wert(t("ps4ota.dlg_dateiname"), name, eingabebreite=60)
    r.zeile_auswahl(t("ps4ota.dlg_kompression"), modus, PFSC_MODI)
    r.zeile_wert(t("ps4ota.dlg_arbeiter"), arbeiter, eingabebreite=5)
    r.haken(t("ps4ota.dlg_nachher_pruefen"), pruefen)
    r.hinweis(t("ps4ota.dlg_zusammen_hinweis"), r.c["fg_warning"])

    def _ok() -> None:
        pfad = ordner.get().strip()
        datei = name.get().strip()
        if not pfad or not datei:
            messagebox.showwarning(t("ps4ota.dlg_zusammen_titel"), t("ps4ota.dlg_ziel_fehlt"), parent=r.win)
            return
        if not datei.lower().endswith(".pkg"):
            datei += ".pkg"
        try:
            n = max(0, int(arbeiter.get().strip() or "1"))
        except ValueError:
            messagebox.showwarning(t("ps4ota.dlg_zusammen_titel"), t("ps4ota.dlg_arbeiter_zahl"), parent=r.win)
            return
        r.antwort.update(ausgabe=os.path.join(pfad, bib.dateiname_bereinigen(datei[:-4]) + ".pkg"),
                         pruefen=pruefen.get(), modus=modus.get(), arbeiter=n)
        r.schliessen()

    ok = r.knoepfe(t("ps4ota.dlg_los"), _ok, t("ps4ota.dlg_abbrechen"))
    r.felder = {"ordner": ordner, "name": name, "pruefen": pruefen, "modus": modus, "arbeiter": arbeiter}   # type: ignore[attr-defined]
    return r, ok


def frage_zusammenfuehren(gui, eltern, basis, update, vorgaben, schrift, pt) -> "dict | None":
    r, _ok = baue_zusammenfuehren(gui, eltern, basis, update, vorgaben, schrift, pt)
    return r.warten()


# ---------------------------------------------------------------------------
# Neu packen
# ---------------------------------------------------------------------------

def baue_neu_packen(gui, eltern, paket: bib.PkgEintrag, vorgaben: dict, schrift: str,
                    pt: Callable[[int], int]) -> "tuple[_Rahmen, tk.Misc]":
    t = gui._t
    r = _Rahmen(gui, eltern, t("ps4ota.dlg_neu_titel"), 700, 430, schrift, pt)
    r.kopf(t("ps4ota.dlg_neu_titel"), t("ps4ota.dlg_neu_untertitel", datei=paket.datei))
    ordner = tk.StringVar(value=vorgaben.get("ordner", paket.ordner))
    stamm = os.path.splitext(paket.datei)[0]
    name = tk.StringVar(value=vorgaben.get("name", stamm + "_repack.pkg"))
    pruefen = tk.BooleanVar(value=bool(vorgaben.get("pruefen", False)))
    modus = tk.StringVar(value=vorgaben.get("modus", "compressed"))
    arbeiter = tk.StringVar(value=str(vorgaben.get("arbeiter", 1)))
    r.zeile_pfad(t("ps4ota.dlg_ziel"), ordner, lambda: _ordner_waehlen(gui, r.win, ordner, t("ps4ota.dlg_ziel_waehlen")))
    r.zeile_wert(t("ps4ota.dlg_dateiname"), name, eingabebreite=60)
    r.zeile_auswahl(t("ps4ota.dlg_kompression"), modus, PFSC_MODI)
    r.zeile_wert(t("ps4ota.dlg_arbeiter"), arbeiter, eingabebreite=5)
    r.haken(t("ps4ota.dlg_nachher_pruefen"), pruefen)
    r.hinweis(t("ps4ota.dlg_neu_hinweis"))

    def _ok() -> None:
        pfad = ordner.get().strip()
        datei = name.get().strip()
        if not pfad or not datei:
            messagebox.showwarning(t("ps4ota.dlg_neu_titel"), t("ps4ota.dlg_ziel_fehlt"), parent=r.win)
            return
        try:
            n = max(0, int(arbeiter.get().strip() or "1"))
        except ValueError:
            messagebox.showwarning(t("ps4ota.dlg_neu_titel"), t("ps4ota.dlg_arbeiter_zahl"), parent=r.win)
            return
        if datei.lower().endswith(".pkg"):
            datei = datei[:-4]
        r.antwort.update(ausgabe=os.path.join(pfad, bib.dateiname_bereinigen(datei) + ".pkg"),
                         pruefen=pruefen.get(), modus=modus.get(), arbeiter=n)
        r.schliessen()

    ok = r.knoepfe(t("ps4ota.dlg_los"), _ok, t("ps4ota.dlg_abbrechen"))
    r.felder = {"ordner": ordner, "name": name, "pruefen": pruefen, "modus": modus, "arbeiter": arbeiter}   # type: ignore[attr-defined]
    return r, ok


def frage_neu_packen(gui, eltern, paket, vorgaben, schrift, pt) -> "dict | None":
    r, _ok = baue_neu_packen(gui, eltern, paket, vorgaben, schrift, pt)
    return r.warten()


# ---------------------------------------------------------------------------
# Bauen aus einem Ordner
# ---------------------------------------------------------------------------

def baue_bauen(gui, eltern, vorgaben: dict, schrift: str, pt: Callable[[int], int]) -> "tuple[_Rahmen, tk.Misc]":
    t = gui._t
    r = _Rahmen(gui, eltern, t("ps4ota.dlg_bauen_titel"), 740, 520, schrift, pt)
    r.kopf(t("ps4ota.dlg_bauen_titel"), t("ps4ota.dlg_bauen_untertitel"))
    quelle = tk.StringVar(value=vorgaben.get("quelle", ""))
    ziel = tk.StringVar(value=vorgaben.get("ziel", ""))
    patch = tk.BooleanVar(value=bool(vorgaben.get("patch", False)))
    pruefen = tk.BooleanVar(value=bool(vorgaben.get("pruefen", False)))
    modus = tk.StringVar(value=vorgaben.get("modus", "compressed"))
    arbeiter = tk.StringVar(value=str(vorgaben.get("arbeiter", 1)))

    def _quelle_waehlen() -> None:
        _ordner_waehlen(gui, r.win, quelle, t("ps4ota.dlg_bauen_quelle_waehlen"))
        if quelle.get().strip() and not ziel.get().strip():
            ziel.set(os.path.normpath(quelle.get().strip().rstrip("\\/") + ".pkg"))

    def _ziel_waehlen() -> None:
        gewaehlt = filedialog.asksaveasfilename(title=t("ps4ota.dlg_bauen_ziel_waehlen"), defaultextension=".pkg",
                                                filetypes=[(t("ps4ota.filetyp_pkg"), "*.pkg")], parent=r.win)
        if gewaehlt:
            ziel.set(os.path.normpath(gewaehlt))

    r.zeile_pfad(t("ps4ota.dlg_bauen_quelle"), quelle, _quelle_waehlen)
    r.zeile_pfad(t("ps4ota.dlg_bauen_ziel"), ziel, _ziel_waehlen)
    r.haken(t("ps4ota.dlg_bauen_patch"), patch)
    r.zeile_auswahl(t("ps4ota.dlg_kompression"), modus, PFSC_MODI)
    r.zeile_wert(t("ps4ota.dlg_arbeiter"), arbeiter, eingabebreite=5)
    r.haken(t("ps4ota.dlg_nachher_pruefen"), pruefen)
    r.hinweis(t("ps4ota.dlg_bauen_hinweis"), r.c["fg_warning"])

    def _ok() -> None:
        ordner = quelle.get().strip()
        datei = ziel.get().strip()
        if not ordner or not os.path.isdir(ordner):
            messagebox.showwarning(t("ps4ota.dlg_bauen_titel"), t("ps4ota.dlg_bauen_quelle_fehlt"), parent=r.win)
            return
        if not os.path.isfile(os.path.join(ordner, "sce_sys", "param.sfo")):
            messagebox.showwarning(t("ps4ota.dlg_bauen_titel"), t("ps4ota.dlg_bauen_ohne_param"), parent=r.win)
            return
        if not datei:
            messagebox.showwarning(t("ps4ota.dlg_bauen_titel"), t("ps4ota.dlg_ziel_fehlt"), parent=r.win)
            return
        try:
            n = max(0, int(arbeiter.get().strip() or "1"))
        except ValueError:
            messagebox.showwarning(t("ps4ota.dlg_bauen_titel"), t("ps4ota.dlg_arbeiter_zahl"), parent=r.win)
            return
        if not datei.lower().endswith(".pkg"):
            datei += ".pkg"
        r.antwort.update(quelle=ordner, ausgabe=datei, patch=patch.get(), pruefen=pruefen.get(),
                         modus=modus.get(), arbeiter=n)
        r.schliessen()

    ok = r.knoepfe(t("ps4ota.dlg_los"), _ok, t("ps4ota.dlg_abbrechen"))
    r.felder = {"quelle": quelle, "ziel": ziel, "patch": patch, "pruefen": pruefen,   # type: ignore[attr-defined]
                "modus": modus, "arbeiter": arbeiter}
    return r, ok


def frage_bauen(gui, eltern, vorgaben, schrift, pt) -> "dict | None":
    r, _ok = baue_bauen(gui, eltern, vorgaben, schrift, pt)
    return r.warten()


# ---------------------------------------------------------------------------
# Vorschau fuer Umbenennen und Verschieben
# ---------------------------------------------------------------------------

def baue_vorschau(gui, eltern, titel: str, untertitel: str, optionen: "list[tuple[str, str]]",
                  plan_fn: "Callable[[str, str], list[bib.Umbenennung]]", schrift: str,
                  pt: Callable[[int], int], *, eigene_eingabe: bool = False,
                  eingabe_text: str = "", feld_titel: str = "", basis_ordner: str = "",
                  mit_ordnerwahl: bool = False) -> "tuple[_Rahmen, tk.Misc]":
    """Ein Dialog mit Auswahl links oben, Vorschau (alt -> neu) in der Mitte und „Ausfuehren“.

    Args:
        optionen: ``[(kennung, anzeigetext)]`` der Auswahlliste.
        plan_fn: ``(kennung, eingabe) -> Plan``; ``eingabe`` ist das Textfeld
            (eigenes Muster oder Ordnername) bzw. der Zielordner.
        eigene_eingabe: Ob es das Textfeld gibt.
        mit_ordnerwahl: Ob zusaetzlich ein Zielordner gewaehlt wird (Verschieben).
    """
    t = gui._t
    r = _Rahmen(gui, eltern, titel, 960, 640, schrift, pt)
    r.kopf(titel, untertitel)
    kennungen = [k for k, _ in optionen]
    anzeige = [a for _, a in optionen]
    wahl = tk.StringVar(value=anzeige[0] if anzeige else "")
    eingabe = tk.StringVar(value=eingabe_text)
    basis = tk.StringVar(value=basis_ordner)

    kopf = tk.Frame(r.koerper, bg=r.c["bg_main"])
    kopf.pack(fill="x", pady=(0, 6))
    # Die Vorschau haengt an der Variablen (``wahl``), nicht am Rueckruf der Pille: Setzt ein Test oder
    # ein Programmteil die Variable, folgt sie mit.
    box = r.look.auswahl(kopf, wahl, anzeige, mindestbreite=360)
    box.pack(side="left")
    eingabefeld = None
    if eigene_eingabe:
        r.look.beschriftung(kopf, feld_titel).pack(side="left", padx=(14, 6))
        eingabefeld = r.look.eingabe(kopf, eingabe, 30)
        eingabefeld.pack(side="left")
    if mit_ordnerwahl:
        ordnerzeile = tk.Frame(r.koerper, bg=r.c["bg_main"])
        ordnerzeile.pack(fill="x", pady=(0, 6))
        r.look.beschriftung(ordnerzeile, t("ps4ota.dlg_ziel"), width=10).pack(side="left")
        r.look.eingabe(ordnerzeile, basis, 20).pack(side="left", fill="x", expand=True, padx=(0, 8))
        r.look.knopf(ordnerzeile, "…", lambda: _ordner_waehlen(gui, r.win, basis, t("ps4ota.dlg_ziel_waehlen")),
                     hoehe=30).pack(side="left")

    # Die Tabelle steht in einer runden Karte. Kleine Wunschgroesse: Eine Tabelle mit dehnbaren Spalten
    # fordert sonst die Breite an, die sie gerade hat (siehe Look.baumrahmen).
    karte = r.look.karte(r.koerper, polster=(8, 8), fuellend=True)
    karte.pack(fill="both", expand=True)
    rahmen = r.look.baumrahmen(karte.innen, 260)
    rahmen.pack(fill="both", expand=True)
    baum = ttk.Treeview(rahmen, columns=("alt", "neu", "hinweis"), show="headings", height=14)
    for spalte, text, breite in (("alt", t("ps4ota.vorschau_alt"), 330), ("neu", t("ps4ota.vorschau_neu"), 430),
                                 ("hinweis", t("ps4ota.vorschau_hinweis"), 120)):
        baum.heading(spalte, text=text, anchor="w")
        baum.column(spalte, width=breite, anchor="w")
    baum.tag_configure("gleich", foreground=r.c["fg_secondary"])
    baum.tag_configure("umbenannt", foreground=r.c["fg_primary"])
    rolle = r.look.rollbalken(rahmen, "vertical", baum.yview)
    rolle.pack(side="right", fill="y")
    baum.pack(side="left", fill="both", expand=True)
    baum.configure(yscrollcommand=rolle.set)
    zaehler = r.look.beschriftung(r.koerper, "")
    zaehler.pack(fill="x", pady=(6, 0))

    zustand: dict = {"plan": []}

    def _aktualisieren(*_args) -> None:
        try:
            kennung = kennungen[anzeige.index(wahl.get())] if anzeige else ""
            plan = plan_fn(kennung, basis.get().strip() if mit_ordnerwahl else eingabe.get())
        except (ValueError, IndexError):
            plan = []
        zustand["plan"] = plan
        baum.delete(*baum.get_children())
        aendert = 0
        for schritt in plan:
            gleich = not schritt.aendert
            aendert += 0 if gleich else 1
            baum.insert("", "end", values=(os.path.basename(schritt.quelle) if not mit_ordnerwahl else schritt.quelle,
                                           os.path.basename(schritt.ziel) if not mit_ordnerwahl else schritt.ziel,
                                           t("ps4ota.vorschau_unveraendert") if gleich else schritt.hinweis),
                        tags=("gleich" if gleich else "umbenannt",))
        zaehler.configure(text=t("ps4ota.vorschau_zaehler", aendern=aendert, gesamt=len(plan)))
        bs.freigeben(ok, bool(aendert))

    for variable in (wahl, eingabe, basis):
        raster.spur_bis_zerstoert(r.win, variable, _aktualisieren)

    def _ok() -> None:
        r.antwort.update(plan=[s for s in zustand["plan"] if s.aendert])
        r.schliessen()

    ok = r.knoepfe(t("ps4ota.vorschau_ausfuehren"), _ok, t("ps4ota.dlg_abbrechen"))
    _aktualisieren()
    r.felder = {"wahl": wahl, "eingabe": eingabe, "basis": basis, "baum": baum,   # type: ignore[attr-defined]
                "zustand": zustand}
    return r, ok


def frage_vorschau(gui, eltern, *args, **kwargs) -> "dict | None":
    r, _ok = baue_vorschau(gui, eltern, *args, **kwargs)
    return r.warten()
