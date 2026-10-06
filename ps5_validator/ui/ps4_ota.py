# -*- coding: utf-8 -*-
"""Das Fenster „PS4 PKG -> OTA“: Sammlung, Einzelheiten, Aufgaben und Netzwerk-Installation.

Seit dem 05.10.2026 der **einzige** Knopf fuer PS4-Pakete unter WEITERE TOOLS
(Nutzerwunsch). Er ersetzt „PS4 PKG -> ffpfsc“, „PS4 PKG -> Dump Ordner“ und
„PS4 & PS5 PKG lesen“. Das Fenster nimmt die Ideen des PS4 PKG Tool von
pearlxcore auf (Sammlung mit Tabelle und Filtern, Einzelheiten, Aufgabenliste,
Umbenennen und Ordnen, Updates, Senden an die Konsole); die PKG-Technik kommt
von OrbisPkgTool (MIT) ueber ``ps5_validator.utils.orbispkg``.

**Aufbau:** oben die Sammlung (Werkzeugzeile, Filter, Tabelle), darunter die
Aktionen, unten ein Notizbuch mit den Einzelheiten des gewaehlten Pakets
(Info, Dateien, Bilder, Interna, Update), dem Netzwerkweg (OTA), der
Aufgabenliste und dem Protokoll.

**Faeden.** Arbeitsfaeden fassen nie ein Widget oder eine Tk-Variable an. Sie
schreiben in ``self._z`` bzw. in die Warteschlange; ein Takt im Hauptfaden
(:meth:`_takt`) traegt das in die Anzeige. Dieselbe Regel wie in den
anderen Fenstern (siehe ``project_tk_faden_variablen``).

Die Texte kommen ueber ``gui._t``; dieses Modul bindet ``i18n`` nicht ein.
"""
from __future__ import annotations

import io
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from ps5_validator.ui import ps4_ota_bausteine as bs
from ps5_validator.ui import ps4_ota_dialoge as dlg
from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import ps4pkg_aufgaben as au
from ps5_validator.utils import ps4pkg_bibliothek as bib
from ps5_validator.utils import ps4pkg_ota as ota
from ps5_validator.utils import ps4pkg_updates as upd
from ps5_validator.utils import orbispkg

logger = logging.getLogger("PS5Converter.ui.ps4_ota")

#: Die Spalten der Tabelle.
SPALTEN = ("datei", "titel", "title_id", "typ", "version", "region", "fw", "groesse", "echtheit", "online", "ordner")
#: Anfangsbreiten bei 100 % (das Fenster rechnet sie mit der Anzeigeskalierung um); die Spalten datei,
#: titel und ordner dehnen sich mit dem Fenster und geben bei Platzmangel nach. Wie breit die Tabelle
#: sein will, spielt fuer das Fenster keine Rolle: ``Look.baumrahmen`` haelt ihren Wunsch klein.
SPALTEN_BREITEN = {"datei": 170, "titel": 160, "title_id": 86, "typ": 64, "version": 64, "region": 52,
                   "fw": 56, "groesse": 74, "echtheit": 82, "online": 64, "ordner": 130}
#: Spalten, die zahlenmaessig sortiert werden.
SORT_ZAHL = {"groesse": lambda e: e.groesse, "version": lambda e: bib.fassung_zahlen(e.app_ver),
             "fw": lambda e: bib.fassung_zahlen(e.system_ver)}

#: Wo die Einstellungen des Fensters stehen.
EINST_QUELLEN = "ps4ota_quellen"
EINST_ZIEL = "ps4ota_ziel"
EINST_IP = "ps4ota_ip"
EINST_PORT = "ps4ota_port"
EINST_ART = "ps4ota_art"
EINST_AUTOLADEN = "ps4ota_autoladen"

#: Die Zielarten des Netzwerkwegs.
ART_DPI = "dpi"
ART_RPI = "rpi"

#: Die Reiter unter der Tabelle, von links nach rechts.
REITER = ("info", "dateien", "bilder", "interna", "update", "ota", "aufgaben", "protokoll")

FENSTER_ATTRIBUT = "_ps4_ota_fenster"


def _zeitstempel() -> str:
    return time.strftime("%H:%M:%S")


class Ps4OtaFenster:
    """Das Fenster. Eine Instanz je geöffnetem Fenster."""

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int], *, autoladen: bool = True) -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.pakete: list[bib.PkgEintrag] = []
        self.sicht: list[bib.PkgEintrag] = []
        self._iid_eintrag: dict[str, bib.PkgEintrag] = {}
        self._sortierung: tuple[str, bool] = ("datei", False)
        self._online: dict[str, str] = {}
        self._update_info: dict[str, upd.UpdateInfo] = {}
        self._z: dict = {"log": [], "aufgaben_geaendert": True, "scan_laeuft": False, "scan_abbruch": False}
        self._log_cursor = 0
        self._gemeldet: set[int] = set()
        self._bilder: dict[str, object] = {}
        self._aktuell: "bib.PkgEintrag | None" = None
        self._schliesst = False
        self._takt_id = None
        self._auswahl_zeitgeber = None
        self.warteschlange = au.Warteschlange(bei_aenderung=self._aufgaben_melden, uebersetzer=self.t)
        # Das Aussehen gehoert dem Programm, nicht dem Fenster: Mit einem eigenen Zeichner je Fenster blieb
        # dessen Bildspeicher (bis 600 Tk-Bilder) nach dem Schliessen stehen.
        self.look = bs.Look.gemeinsam(gui, schrift, mono, pt)
        self._bauen()
        self._takt()
        gespeichert = [q for q in (self._einstellung(EINST_QUELLEN, []) or []) if isinstance(q, str)]
        if autoladen and gespeichert and self._einstellung(EINST_AUTOLADEN, True):
            self._einlesen([q for q in gespeichert if os.path.exists(q)], ersetzen=True)

    # ------------------------------------------------------------------
    # Hilfen
    # ------------------------------------------------------------------
    def _einstellung(self, schluessel: str, vorgabe):
        try:
            return self.g._load_setting(schluessel, vorgabe)
        except Exception:  # noqa: BLE001
            return vorgabe

    def _merken(self, schluessel: str, wert) -> None:
        try:
            self.g._save_setting(schluessel, wert)
        except Exception:  # noqa: BLE001
            logger.debug("Einstellung nicht gespeichert: %s", schluessel, exc_info=True)

    def _aufgaben_melden(self) -> None:
        self._z["aufgaben_geaendert"] = True

    def _log(self, text: str) -> None:
        self._z["log"].append("[%s] %s" % (_zeitstempel(), text))

    def _beschriftung(self, eltern, text: str, **kw) -> tk.Label:
        return self.look.beschriftung(eltern, text, **kw)

    def _knopf(self, eltern, text: str, befehl, *, akzent: bool = False, chevron: bool = False, fett: bool = False,
               hoehe: float = 30, breite: "int | None" = None):
        """Ein Knopf als Pille auf der Farbe seines Elternteils (``Look.knopf``)."""
        return self.look.knopf(eltern, text, befehl, akzent=akzent, chevron=chevron, fett=fett, hoehe=hoehe,
                               breite=breite)

    def _hinweis(self, eltern, text: str, farbe: "str | None" = None) -> tk.Label:
        return self.look.hinweis(eltern, text, farbe)

    def _baumrahmen(self, eltern, hoehe: int = 110) -> tk.Frame:
        """Ein Rahmen fuer eine Tabelle, der seine Groesse nicht von ihr borgt (``Look.baumrahmen``)."""
        return self.look.baumrahmen(eltern, hoehe)

    def _menue(self) -> tk.Menu:
        return tk.Menu(self.win, tearoff=0, bg=self.c["bg_card"], fg=self.c["fg_primary"],
                       activebackground=self.c["fg_accent"], activeforeground=self.c["bg_main"],
                       font=(self.F, self.pt(9)))

    def _fehler(self, schluessel: str, **werte) -> None:
        messagebox.showwarning(self.t("ps4ota.window_title"), self.t(schluessel, **werte), parent=self.win)

    def _werkzeug_da(self) -> bool:
        """Gibt es OrbisPkgTool fuer diesen Rechner? Sonst sagt das Fenster es."""
        if orbispkg.verfuegbar():
            return True
        messagebox.showerror(self.t("ps4ota.window_title"),
                             self.t("ps4ota.kein_werkzeug", ordner=orbispkg.WERKZEUGORDNER,
                                    plattform=orbispkg.plattformordner()), parent=self.win)
        return False

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _bauen(self) -> None:
        g, t = self.g, self.t
        titel = t("ps4ota.window_title")
        # Die Mindesthoehe waechst mit der Anzeigeskalierung: Kopfkarte, die kleinsten Teile der beiden
        # Bereiche und die Statuszeile brauchen bei 125 % rund 820 Punkte, bei 100 % rund 660.
        self.win = g._build_modern_toplevel(titel, 1260, 900, min_width=1080,
                                            min_height=max(720, int(round(660 * self.look.z.faktor))))
        g._build_modern_header(self.win, titel, t("ps4ota.subtitle"))
        # Unten zuerst packen, sonst quetscht die Mindestgroesse die Leiste (test_fensterlayout).
        self._statusleiste = tk.Frame(self.win, bg=self.c["bg_main"], padx=18, pady=4)
        self._statusleiste.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value=t("ps4ota.status_leer"))
        tk.Label(self._statusleiste, textvariable=self.status_var, font=(self.F, self.pt(9)), bg=self.c["bg_main"],
                 fg=self.c["fg_secondary"], anchor="w").pack(side="left", fill="x", expand=True)
        # Das Fenster hat Laeufe (Aufgaben): Es soll sich nicht nur ueber das X der Titelleiste schliessen lassen
        # (test_fensterknoepfe). Zuerst gepackt, steht der Knopf ganz rechts; "Einlesen abbrechen" kommt links davon.
        self._schliessen_knopf = self._knopf(self._statusleiste, t("action.close"), self._schliessen, hoehe=26)
        self._schliessen_knopf.pack(side="right", padx=(8, 0))
        self._abbruch_scan = self._knopf(self._statusleiste, t("ps4ota.scan_abbrechen"), self._scan_abbrechen, hoehe=26)
        self._abbruch_scan.pack(side="right")
        self._abbruch_scan.pack_forget()
        koerper = tk.Frame(self.win, bg=self.c["bg_main"], padx=18)
        koerper.pack(fill="both", expand=True)
        self._baue_kopfkarte(koerper)
        px = self.look.z.px
        # width/height: Ohne sie fordert das Fenster die Breite an, die es gerade hat, und
        # waechst im Aufbau von selbst (siehe Look.baumrahmen).
        geteilt = tk.PanedWindow(koerper, orient="vertical", sashwidth=px(8), bg=self.c["bg_main"],
                                 sashrelief="flat", bd=0, width=100, height=px(380))
        geteilt.pack(fill="both", expand=True, pady=(0, 0))
        oben = tk.Frame(geteilt, bg=self.c["bg_main"])
        unten = tk.Frame(geteilt, bg=self.c["bg_main"])
        geteilt.add(oben, minsize=px(200), stretch="always")
        geteilt.add(unten, minsize=px(240), stretch="always")
        self._baue_tabelle(oben)
        self._baue_aktionen(oben)
        self._baue_reiter(unten)
        self.win.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.win.bind("<Destroy>", self._bei_zerstoerung, add="+")
        self._aktionen_pruefen()

    # -- Kopfkarte: Werkzeuge, Suche und Filter ------------------------------------
    def _baue_kopfkarte(self, eltern) -> None:
        t, look = self.t, self.look
        karte = look.karte(eltern, polster=(14, 10))
        karte.pack(fill="x", pady=(2, 8))
        zeile1 = look.fluss(karte.innen, abstand=(8, 6))
        zeile1.pack(fill="x")
        for text, befehl in ((t("ps4ota.btn_ordner"), self._ordner_laden),
                             (t("ps4ota.btn_dateien"), self._dateien_hinzufuegen),
                             (t("ps4ota.btn_neu_einlesen"), self._neu_einlesen),
                             (t("ps4ota.btn_leeren"), self._liste_leeren)):
            zeile1.hinzufuegen(self._knopf(zeile1, text, befehl))
        self.suche_var = tk.StringVar()
        self.suche_eingabe = look.suche(zeile1, self.suche_var, t("ps4ota.such_platzhalter"))
        zeile1.hinzufuegen(self.suche_eingabe, flex=True, min_breite=220)
        raster.spur_bis_zerstoert(self.win, self.suche_var, lambda *_: self._tabelle_neu())

        zeile2 = look.fluss(karte.innen, abstand=(14, 6))
        zeile2.pack(fill="x", pady=(8, 0))
        self.typ_var = tk.StringVar(value=t("ps4ota.alle"))
        self.region_var = tk.StringVar(value=t("ps4ota.alle"))
        self.echt_var = tk.StringVar(value=t("ps4ota.alle"))
        self.gruppe_var = tk.StringVar(value=t("ps4ota.gruppe_keine"))
        self._typ_namen = {t("ps4ota.alle"): "", t("ps4ota.typ_base"): bib.TYP_BASIS, t("ps4ota.typ_patch"): bib.TYP_UPDATE,
                           t("ps4ota.typ_addon"): bib.TYP_ZUSATZ, t("ps4ota.typ_app"): bib.TYP_APP,
                           t("ps4ota.typ_unbekannt"): bib.TYP_UNBEKANNT}
        self._echt_namen = {t("ps4ota.alle"): "", t("ps4ota.echt_fake"): bib.ECHT_FAKE,
                            t("ps4ota.echt_official"): bib.ECHT_OFFIZIELL, t("ps4ota.echt_official_dp"): bib.ECHT_OFFIZIELL_DP}
        self._gruppen_namen = {t("ps4ota.gruppe_keine"): "", t("ps4ota.col_titel"): "titel",
                               t("ps4ota.col_title_id"): "title_id", t("ps4ota.col_kategorie"): "kategorie",
                               t("ps4ota.col_fw"): "system_ver", t("ps4ota.col_typ"): "typ"}
        self._region_box = None
        for beschriftung, var, werte in ((t("ps4ota.col_typ"), self.typ_var, list(self._typ_namen)),
                                         (t("ps4ota.col_region"), self.region_var, [t("ps4ota.alle")]),
                                         (t("ps4ota.col_echtheit"), self.echt_var, list(self._echt_namen)),
                                         (t("ps4ota.gruppieren"), self.gruppe_var, list(self._gruppen_namen))):
            # Beschriftung und Auswahl sind ein Kind der Zeile: Sie brechen zusammen um.
            gruppe = tk.Frame(zeile2, bg=self.c["bg_card"])
            self._beschriftung(gruppe, beschriftung).pack(side="left", padx=(0, 6))
            box = look.auswahl(gruppe, var, werte, befehl=self._tabelle_neu, mindestbreite=96)
            box.pack(side="left")
            zeile2.hinzufuegen(gruppe)
            if var is self.region_var:
                self._region_box = box
        zeile2.hinzufuegen(self._knopf(zeile2, t("ps4ota.filter_loeschen"), self._filter_loeschen))

    # -- Tabelle -----------------------------------------------------------
    def _baue_tabelle(self, eltern) -> None:
        look = self.look
        karte = look.karte(eltern, polster=(8, 8), fuellend=True)
        # Die Aktionsleiste kommt darunter; die Tabelle nimmt den Rest (erst packen, was fest ist - s. _baue_aktionen).
        self._tabellenrahmen = karte
        rahmen = self._baumrahmen(karte.innen, 150)
        rahmen.pack(fill="both", expand=True)
        px = look.z.px
        self.baum = ttk.Treeview(rahmen, columns=SPALTEN, show="headings", selectmode="extended", height=6)
        for spalte in SPALTEN:
            dehnt = spalte in ("datei", "titel", "ordner")
            self.baum.heading(spalte, text=self.t("ps4ota.col_" + spalte), anchor="w",
                              command=lambda s=spalte: self._sortieren(s))
            self.baum.column(spalte, width=px(SPALTEN_BREITEN[spalte]), minwidth=px(80 if dehnt else 40),
                             anchor="e" if spalte in ("groesse",) else "w", stretch=dehnt)
        self.baum.tag_configure("unlesbar", foreground=self.c["fg_warning"])
        self.baum.tag_configure("update", foreground=self.c["fg_accent"])
        self.baum.tag_configure("addon", foreground=self.c["fg_secondary"])
        self.baum.tag_configure("neuer", foreground=self.c["fg_success"])
        self.baum.tag_configure("gruppe", foreground=self.c["fg_accent"])
        senkrecht = look.rollbalken(rahmen, "vertical", self.baum.yview)
        waagerecht = look.rollbalken(rahmen, "horizontal", self.baum.xview)
        self.baum.configure(yscrollcommand=senkrecht.set, xscrollcommand=waagerecht.set)
        waagerecht.pack(side="bottom", fill="x")
        senkrecht.pack(side="right", fill="y")
        self.baum.pack(side="left", fill="both", expand=True)
        self.baum.bind("<<TreeviewSelect>>", self._auswahl_geaendert)
        self.baum.bind("<Button-3>", self._kontextmenue)
        self.baum.bind("<Double-1>", lambda e: self._notizbuch_waehlen("info"))

    def _baue_aktionen(self, eltern) -> None:
        t = self.t
        # Eine umbrechende Zeile: Bei 1260 Punkten und deutschem Text reichte die Breite nicht
        # fuer alle neun Knoepfe, der letzte stand abgeschnitten am Rand.
        leiste = self.look.fluss(eltern, abstand=(8, 6))
        leiste.pack(side="bottom", fill="x", pady=(8, 2))
        self._tabellenrahmen.pack(side="top", fill="both", expand=True)
        self.knoepfe: dict[str, object] = {}

        def neu(schluessel: str, text: str, befehl, **kw):
            knopf = self._knopf(leiste, text, befehl, fett=True, hoehe=32, **kw)
            leiste.hinzufuegen(knopf)
            self.knoepfe[schluessel] = knopf
            return knopf

        neu("entpacken", t("ps4ota.btn_entpacken"), self._aktion_entpacken)
        neu("ffpfsc", t("ps4ota.btn_ffpfsc"), self._aktion_ffpfsc)
        neu("zusammen", t("ps4ota.btn_zusammen"), self._aktion_zusammenfuehren)
        neu("neu_packen", t("ps4ota.btn_neu_packen"), self._aktion_neu_packen)
        neu("pruefen", t("ps4ota.btn_pruefen"), self._aktion_pruefen)
        neu("umbenennen", t("ps4ota.btn_umbenennen"), self._aktion_umbenennen)
        neu("verschieben", t("ps4ota.btn_verschieben"), self._aktion_verschieben)
        neu("ota", t("ps4ota.btn_ota"), self._aktion_ota_senden, akzent=True)
        mehr = neu("mehr", t("ps4ota.btn_mehr"), None, chevron=True)
        mehr.configure(command=lambda: self._mehr_menue(mehr))
        self.auswahl_var = tk.StringVar(value="")
        zaehler = tk.Label(leiste, textvariable=self.auswahl_var, font=(self.F, self.pt(9)), bg=self.c["bg_main"],
                           fg=self.c["fg_secondary"])
        leiste.hinzufuegen(zaehler, rechts=True)

    # -- Reiter ------------------------------------------------------------
    def _baue_reiter(self, eltern) -> None:
        """Die Einzelheiten: eine Reihe Chips und darunter die Seite des gewaehlten Chips in einer runden Karte."""
        self._reiter_var = tk.StringVar(value=REITER[0])
        self._reiter = self.look.chips(eltern, [(k, self.t("ps4ota.tab_" + k)) for k in REITER], self._reiter_var)
        self._reiter.pack(side="top", anchor="w", pady=(0, 6))
        karte = self.look.karte(eltern, polster=(12, 10), fuellend=True)
        karte.pack(side="top", fill="both", expand=True)
        self._seitenkarte = karte
        self._seiten: dict[str, tk.Frame] = {}
        bauer = {"info": self._baue_info, "dateien": self._baue_dateien, "bilder": self._baue_bilder,
                 "interna": self._baue_interna, "update": self._baue_update, "ota": self._baue_ota,
                 "aufgaben": self._baue_aufgaben, "protokoll": self._baue_protokoll}
        for schluessel in REITER:
            seite = tk.Frame(karte.innen, bg=self.c["bg_card"])
            self._seiten[schluessel] = seite
            bauer[schluessel](seite)
        raster.spur_bis_zerstoert(self.win, self._reiter_var, lambda *_: self._seite_gewechselt())
        self._seite_gewechselt()

    def _notizbuch_waehlen(self, schluessel: str) -> None:
        if schluessel in self._seiten:
            self._reiter_var.set(schluessel)

    def _aktuelle_seite(self) -> str:
        return self._reiter_var.get()

    def _seite_gewechselt(self, _e=None) -> None:
        aktuell = self._aktuelle_seite()
        for schluessel, seite in self._seiten.items():
            if schluessel == aktuell:
                seite.pack(fill="both", expand=True)
            else:
                seite.pack_forget()
        if aktuell == "dateien":
            self._dateien_laden()

    # -- Info ----------------------------------------------------------------
    def _baue_info(self, seite) -> None:
        look = self.look
        links = tk.Frame(seite, bg=self.c["bg_card"], width=look.z.px(176))
        links.pack(side="left", fill="y", padx=(0, 12))
        links.pack_propagate(False)
        bildkarte = look.karte(links, fuellung="console_bg", polster=(6, 6))
        bildkarte.pack(anchor="n")
        self.icon_label = tk.Label(bildkarte.innen, bg=self.c["console_bg"], fg=self.c["fg_secondary"], width=16,
                                   height=8, text="", anchor="center", font=(self.F, self.pt(9)))
        self.icon_label.pack()
        info_rahmen = self._baumrahmen(seite, 110)
        info_rahmen.pack(side="left", fill="both", expand=True)
        self.info_baum = ttk.Treeview(info_rahmen, columns=("feld", "wert"), show="headings", height=8)
        self.info_baum.heading("feld", text=self.t("ps4ota.info_feld"), anchor="w")
        self.info_baum.heading("wert", text=self.t("ps4ota.info_wert"), anchor="w")
        self.info_baum.column("feld", width=look.z.px(160), anchor="w", stretch=False)
        self.info_baum.column("wert", width=look.z.px(260), anchor="w")
        self.info_baum.tag_configure("abschnitt", foreground=self.c["fg_accent"])
        rolle = look.rollbalken(info_rahmen, "vertical", self.info_baum.yview)
        self.info_baum.configure(yscrollcommand=rolle.set)
        rolle.pack(side="right", fill="y")
        self.info_baum.pack(side="left", fill="both", expand=True)
        self.info_baum.bind("<Button-3>", self._info_menue)

    # -- Dateien -------------------------------------------------------------
    def _baue_dateien(self, seite) -> None:
        t, look = self.t, self.look
        leiste = look.fluss(seite, abstand=(8, 6))
        leiste.pack(side="top", fill="x", pady=(0, 6))
        for text, befehl in ((t("ps4ota.dateien_laden"), lambda: self._dateien_laden(erzwingen=True)),
                             (t("ps4ota.dateien_entpacken"), self._dateien_auswahl_entpacken),
                             (t("ps4ota.dateien_exportieren"), self._dateien_exportieren)):
            leiste.hinzufuegen(self._knopf(leiste, text, befehl))
        self.dateien_status = tk.StringVar(value=t("ps4ota.dateien_leer"))
        status = tk.Label(leiste, textvariable=self.dateien_status, font=(self.F, self.pt(9)), bg=self.c["bg_card"],
                          fg=self.c["fg_secondary"], anchor="w")
        leiste.hinzufuegen(status, flex=True, min_breite=160)
        rahmen = self._baumrahmen(seite, 100)
        rahmen.pack(fill="both", expand=True)
        self.dateien_baum = ttk.Treeview(rahmen, columns=("groesse",), show="tree headings", selectmode="extended", height=8)
        self.dateien_baum.heading("#0", text=t("ps4ota.dateien_name"), anchor="w")
        self.dateien_baum.heading("groesse", text=t("ps4ota.col_groesse"), anchor="e")
        self.dateien_baum.column("#0", width=look.z.px(300), anchor="w")
        self.dateien_baum.column("groesse", width=look.z.px(90), anchor="e", stretch=False)
        rolle = look.rollbalken(rahmen, "vertical", self.dateien_baum.yview)
        self.dateien_baum.configure(yscrollcommand=rolle.set)
        rolle.pack(side="right", fill="y")
        self.dateien_baum.pack(side="left", fill="both", expand=True)
        self._dateien_eintraege: dict[str, str] = {}      # Knoten -> Pfad im Paket
        self._dateien_ist_datei: set[str] = set()         # Knoten, die Dateien sind (keine Ordner)
        self._dateien_fuer: str = ""

    # -- Bilder ----------------------------------------------------------------
    def _baue_bilder(self, seite) -> None:
        t, look = self.t, self.look
        self._bild_labels: dict[str, tk.Label] = {}
        for schluessel, kennung in (("icon0", bib.EINTRAG_ICON0), ("pic0", bib.EINTRAG_PIC0), ("pic1", bib.EINTRAG_PIC1)):
            spalte = tk.Frame(seite, bg=self.c["bg_card"])
            spalte.pack(side="left", fill="y", padx=(0, 16))
            self._beschriftung(spalte, t("ps4ota.bild_" + schluessel)).pack(anchor="w")
            bildkarte = look.karte(spalte, fuellung="console_bg", polster=(6, 6))
            bildkarte.pack(anchor="nw", pady=(4, 8))
            # Ohne Bild zaehlt die Breite in Zeichen; mit Bild stellt _bilder_zeigen auf Bildpunkte um.
            etikett = tk.Label(bildkarte.innen, bg=self.c["console_bg"], fg=self.c["fg_secondary"], width=16, height=6,
                               text="", font=(self.F, self.pt(9)))
            etikett.pack()
            self._bild_labels[schluessel] = etikett
            self._knopf(spalte, t("ps4ota.bild_speichern"),
                        lambda k=kennung, s=schluessel: self._bild_speichern(k, s)).pack(anchor="w")

    # -- Interna -----------------------------------------------------------------
    def _baue_interna(self, seite) -> None:
        t, look = self.t, self.look
        self.interna_kopf = tk.StringVar(value="")
        tk.Label(seite, textvariable=self.interna_kopf, font=(self.M, self.pt(9)), bg=self.c["bg_card"],
                 fg=self.c["fg_secondary"], anchor="w", justify="left").pack(side="top", fill="x")
        rahmen = self._baumrahmen(seite, 100)
        rahmen.pack(fill="both", expand=True, pady=(6, 0))
        spalten = ("kennung", "name", "groesse", "offset", "verschluesselt")
        self.interna_baum = ttk.Treeview(rahmen, columns=spalten, show="headings", height=8)
        for s, breite in (("kennung", 70), ("name", 190), ("groesse", 80), ("offset", 80), ("verschluesselt", 90)):
            self.interna_baum.heading(s, text=t("ps4ota.interna_" + s), anchor="w")
            self.interna_baum.column(s, width=look.z.px(breite), anchor="e" if s in ("groesse", "offset") else "w",
                                     stretch=s == "name")
        rolle = look.rollbalken(rahmen, "vertical", self.interna_baum.yview)
        self.interna_baum.configure(yscrollcommand=rolle.set)
        rolle.pack(side="right", fill="y")
        self.interna_baum.pack(side="left", fill="both", expand=True)

    # -- Update --------------------------------------------------------------------
    def _baue_update(self, seite) -> None:
        t, look = self.t, self.look
        leiste = look.fluss(seite, abstand=(8, 6))
        leiste.pack(side="top", fill="x", pady=(0, 6))
        self.update_nachsehen = self._knopf(leiste, t("ps4ota.update_nachsehen"), self._aktion_update_online)
        self.update_laden = self._knopf(leiste, t("ps4ota.update_laden"), self._aktion_update_laden)
        self.update_alle = self._knopf(leiste, t("ps4ota.update_alle"), self._aktion_alle_online)
        for knopf in (self.update_nachsehen, self.update_laden, self.update_alle):
            leiste.hinzufuegen(knopf)
        self._hinweis(seite, t("ps4ota.update_hinweis")).pack(side="bottom", fill="x", pady=(6, 0))
        karte = look.karte(seite, fuellung="console_bg", polster=(6, 6), fuellend=True)
        karte.pack(fill="both", expand=True)
        self.update_text = tk.Text(karte.innen, height=8, width=40, font=(self.M, self.pt(9)), bg=self.c["console_bg"],
                                   fg=self.c["fg_primary"], relief="flat", wrap="word", padx=10, pady=6)
        rolle = look.rollbalken(karte.innen, "vertical", self.update_text.yview, tief=True)
        self.update_text.configure(yscrollcommand=rolle.set, state="disabled")
        rolle.pack(side="right", fill="y")
        self.update_text.pack(side="left", fill="both", expand=True)

    def _update_schreiben(self, text: str) -> None:
        self.update_text.configure(state="normal")
        self.update_text.delete("1.0", "end")
        self.update_text.insert("1.0", text)
        self.update_text.configure(state="disabled")

    # -- OTA ---------------------------------------------------------------------------
    def _baue_ota(self, seite) -> None:
        t, look = self.t, self.look
        self.ota_art_var = tk.StringVar(value=str(self._einstellung(EINST_ART, ART_DPI)))
        if self.ota_art_var.get() not in (ART_DPI, ART_RPI):
            self.ota_art_var.set(ART_DPI)
        ip = str(self._einstellung(EINST_IP, "") or "")
        if not ip:
            try:
                ip = self.g._ps5_ip("")
            except Exception:  # noqa: BLE001
                ip = ""
        self.ota_ip_var = tk.StringVar(value=ip)
        self.ota_port_var = tk.StringVar(value=str(self._einstellung(EINST_PORT, ota.STANDARD_PORT)))
        self.ota_pc_var = tk.StringVar(value=t("ps4ota.ota_pc_auto"))
        self.ota_serverport_var = tk.StringVar(value="0")
        self.ota_status_var = tk.StringVar(value="")
        karte = self.c["bg_card"]
        # Beide Beschriftungen gleich breit, damit die Felder untereinander stehen.
        breite = max(len(t("ps4ota.ota_ip")), len(t("ps4ota.ota_pc"))) + 2
        zeile = tk.Frame(seite, bg=karte)
        zeile.pack(fill="x", pady=(0, 8))
        self.ota_art_chips = look.chips(zeile, [(ART_DPI, t("ps4ota.ota_art_dpi")), (ART_RPI, t("ps4ota.ota_art_rpi"))],
                                        self.ota_art_var, befehl=self._ota_art_geaendert)
        self.ota_art_chips.pack(side="left")
        zeile2 = tk.Frame(seite, bg=karte)
        zeile2.pack(fill="x", pady=3)
        self._beschriftung(zeile2, t("ps4ota.ota_ip"), width=breite).pack(side="left")
        look.eingabe(zeile2, self.ota_ip_var, 18).pack(side="left")
        self._beschriftung(zeile2, t("ps4ota.ota_port")).pack(side="left", padx=(16, 6))
        look.eingabe(zeile2, self.ota_port_var, 7).pack(side="left")
        self._knopf(zeile2, t("ps4ota.ota_erkennen"), self._ota_erkennen).pack(side="left", padx=(14, 0))
        self.ota_erkannt = tk.StringVar(value="")
        tk.Label(zeile2, textvariable=self.ota_erkannt, font=(self.F, self.pt(9)), bg=karte,
                 fg=self.c["fg_success"], anchor="w").pack(side="left", padx=(12, 0))
        self.ota_rpi_zeile = tk.Frame(seite, bg=karte)
        self.ota_rpi_zeile.pack(fill="x", pady=3)
        self._beschriftung(self.ota_rpi_zeile, t("ps4ota.ota_pc"), width=breite).pack(side="left")
        # Frei tippbar; das Menue daneben bietet "automatisch" und die Adressen dieses Rechners an.
        self.ota_pc_eingabe = look.eingabe(self.ota_rpi_zeile, self.ota_pc_var, 20)
        self.ota_pc_eingabe.pack(side="left")
        self.ota_pc_menue = look.menue_knopf(
            self.ota_rpi_zeile, t("ps4ota.ota_pc_waehlen"),
            lambda: [t("ps4ota.ota_pc_auto")] + ota.lokale_adressen(), self.ota_pc_var.set)
        self.ota_pc_menue.pack(side="left", padx=(8, 0))
        self._beschriftung(self.ota_rpi_zeile, t("ps4ota.ota_serverport")).pack(side="left", padx=(16, 6))
        look.eingabe(self.ota_rpi_zeile, self.ota_serverport_var, 7).pack(side="left")
        zeile4 = tk.Frame(seite, bg=karte)
        zeile4.pack(fill="x", pady=(10, 2))
        self._ota_knopfzeile = zeile4
        self.ota_senden = self._knopf(zeile4, t("ps4ota.ota_senden"), self._aktion_ota_senden, akzent=True, hoehe=32)
        self.ota_senden.pack(side="left")
        self.ota_pruefen = self._knopf(zeile4, t("ps4ota.ota_installiert"), self._ota_installiert, hoehe=32)
        self.ota_pruefen.pack(side="left", padx=(8, 0))
        self.ota_loeschen = self._knopf(zeile4, t("ps4ota.ota_deinstallieren"), None, hoehe=32, chevron=True)
        self.ota_loeschen.configure(command=lambda: self._ota_deinstallieren_menue(self.ota_loeschen))
        self.ota_loeschen.pack(side="left", padx=(8, 0))
        tk.Label(seite, textvariable=self.ota_status_var, font=(self.F, self.pt(9)), bg=karte,
                 fg=self.c["fg_secondary"], anchor="w").pack(fill="x", pady=(6, 0))
        self.ota_hinweis = self._hinweis(seite, "")
        self.ota_hinweis.pack(fill="x", pady=(2, 0))
        self._ota_art_geaendert()

    def _ota_art_geaendert(self) -> None:
        art = self.ota_art_var.get()
        t = self.t
        if art == ART_RPI:
            self.ota_rpi_zeile.pack(fill="x", pady=3, before=self._ota_knopfzeile)
            self.ota_hinweis.configure(text=t("ps4ota.ota_hinweis_rpi"))
        else:
            self.ota_rpi_zeile.pack_forget()
            self.ota_hinweis.configure(text=t("ps4ota.ota_hinweis_dpi"))
        # "Ist installiert?" und "Deinstallieren" gibt es nur beim Remote Package Installer.
        bs.freigeben(self.ota_pruefen, art == ART_RPI)
        bs.freigeben(self.ota_loeschen, art == ART_RPI)
        self._merken(EINST_ART, art)

    # -- Aufgaben ------------------------------------------------------------------------
    def _baue_aufgaben(self, seite) -> None:
        t, look = self.t, self.look
        leiste = look.fluss(seite, abstand=(8, 6))
        leiste.pack(side="top", fill="x", pady=(0, 6))
        self.aufg_knoepfe: dict[str, object] = {}
        for schluessel, befehl in (("abbrechen", self._aufgabe_abbrechen), ("wiederholen", self._aufgabe_wiederholen),
                                   ("entfernen", self._aufgabe_entfernen), ("leeren", self._aufgaben_leeren),
                                   ("oeffnen", self._aufgabe_oeffnen)):
            knopf = self._knopf(leiste, t("ps4ota.aufg_" + schluessel), befehl)
            leiste.hinzufuegen(knopf)
            self.aufg_knoepfe[schluessel] = knopf
        self.aufg_gesamt = look.balken(leiste, breite=220, hoehe=12)
        leiste.hinzufuegen(self.aufg_gesamt, rechts=True)
        rahmen = self._baumrahmen(seite, 100)
        rahmen.pack(fill="both", expand=True)
        spalten = ("art", "titel", "status", "prozent", "meldung")
        self.aufg_baum = ttk.Treeview(rahmen, columns=spalten, show="headings", height=7, selectmode="browse")
        for s, breite, anker in (("art", 80, "w"), ("titel", 190, "w"), ("status", 70, "w"), ("prozent", 45, "e"),
                                 ("meldung", 260, "w")):
            self.aufg_baum.heading(s, text=t("ps4ota.aufg_col_" + s), anchor="w")
            self.aufg_baum.column(s, width=look.z.px(breite), anchor=anker, stretch=s in ("meldung", "titel"))
        self.aufg_baum.tag_configure("fehler", foreground=self.c["fg_warning"])
        self.aufg_baum.tag_configure("fertig", foreground=self.c["fg_success"])
        self.aufg_baum.tag_configure("laeuft", foreground=self.c["fg_accent"])
        rolle = look.rollbalken(rahmen, "vertical", self.aufg_baum.yview)
        self.aufg_baum.configure(yscrollcommand=rolle.set)
        rolle.pack(side="right", fill="y")
        self.aufg_baum.pack(side="left", fill="both", expand=True)
        self.aufg_baum.bind("<<TreeviewSelect>>", lambda e: self._aufgaben_knoepfe())

    # -- Protokoll -----------------------------------------------------------------------
    def _baue_protokoll(self, seite) -> None:
        look = self.look
        karte = look.karte(seite, fuellung="console_bg", polster=(6, 6), fuellend=True)
        karte.pack(fill="both", expand=True)
        self.protokoll = tk.Text(karte.innen, height=6, width=40, font=(self.M, self.pt(9)), bg=self.c["console_bg"],
                                 fg=self.c["console_fg"], relief="flat", wrap="none", padx=10, pady=6)
        rolle = look.rollbalken(karte.innen, "vertical", self.protokoll.yview, tief=True)
        self.protokoll.configure(yscrollcommand=rolle.set)
        rolle.pack(side="right", fill="y")
        self.protokoll.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------------
    # Sammlung: einlesen, filtern, anzeigen
    # ------------------------------------------------------------------
    def _zwischenspeicher(self) -> "bib.Zwischenspeicher":
        try:
            from ps5_validator.utils.einstellungen import konfigurationsordner
            return bib.Zwischenspeicher(os.path.join(konfigurationsordner(), "ps4ota_sammlung.json"))
        except Exception:  # noqa: BLE001
            return bib.Zwischenspeicher("")

    def _ordner_laden(self) -> None:
        ordner = filedialog.askdirectory(title=self.t("ps4ota.ordner_waehlen"),
                                         initialdir=self.g._get_source_dialog_initial_dir() or None, parent=self.win)
        if ordner:
            self.g._remember_source_dialog_path(ordner)
            self._quelle_aufnehmen(os.path.normpath(ordner))

    def _dateien_hinzufuegen(self) -> None:
        dateien = filedialog.askopenfilenames(title=self.t("ps4ota.dateien_waehlen"),
                                              filetypes=[(self.t("ps4ota.filetyp_pkg"), "*.pkg"),
                                                         (self.t("ps4ota.filetyp_alle"), "*.*")], parent=self.win)
        for pfad in dateien:
            self._quelle_aufnehmen(os.path.normpath(pfad), nur_datei=True)

    def _quelle_aufnehmen(self, pfad: str, nur_datei: bool = False) -> None:
        """Merkt eine Quelle (Ordner oder Datei) und liest sie ein."""
        quellen = [q for q in (self._einstellung(EINST_QUELLEN, []) or []) if isinstance(q, str)]
        if os.path.normcase(pfad) not in [os.path.normcase(q) for q in quellen]:
            quellen.append(pfad)
            self._merken(EINST_QUELLEN, quellen[-40:])
        self._einlesen([pfad], ersetzen=False)

    def _neu_einlesen(self) -> None:
        quellen = [q for q in (self._einstellung(EINST_QUELLEN, []) or []) if isinstance(q, str) and os.path.exists(q)]
        if not quellen:
            self._fehler("ps4ota.keine_quellen")
            return
        self._einlesen(quellen, ersetzen=True)

    def _liste_leeren(self) -> None:
        self.pakete = []
        self._merken(EINST_QUELLEN, [])
        self._tabelle_neu()
        self._details_leeren()
        self.status_var.set(self.t("ps4ota.status_leer"))

    def _einlesen(self, quellen: list, ersetzen: bool) -> None:
        if self._z.get("scan_laeuft") or not quellen:
            return
        self._z.update(scan_laeuft=True, scan_abbruch=False, scan_text=None, scan_suche=None, scan_ergebnis=None,
                       scan_fehler="")
        zwischen = self._zwischenspeicher()
        self._abbruch_scan.pack(side="right")
        self.status_var.set(self.t("ps4ota.scan_laeuft"))

        def arbeit() -> None:
            try:
                erg = bib.einlesen(quellen, fortschritt=lambda a, g, d: self._z.__setitem__("scan_text", (a, g, d)),
                                   abbruch=lambda: self._z.get("scan_abbruch", False), zwischenspeicher=zwischen,
                                   suche_fortschritt=lambda n, ordner: self._z.__setitem__("scan_suche", (n, ordner)))
                self._z["scan_ergebnis"] = (erg, ersetzen)
            except Exception as fehler:  # noqa: BLE001
                logger.exception("Einlesen gescheitert")
                self._z["scan_fehler"] = str(fehler)
            finally:
                self._z["scan_laeuft"] = False
                self._z["scan_fertig"] = True

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-scan").start()

    def _scan_abbrechen(self) -> None:
        self._z["scan_abbruch"] = True

    def _scan_fertig(self) -> None:
        ergebnis = self._z.pop("scan_ergebnis", None)
        fehler = self._z.pop("scan_fehler", "")
        self._z["scan_fertig"] = False
        self._abbruch_scan.pack_forget()
        if fehler:
            self._log(self.t("ps4ota.log_scan_fehler", fehler=fehler))
            self.status_var.set(self.t("ps4ota.scan_fehler"))
            return
        if ergebnis is None:
            return
        neue, ersetzen = ergebnis
        if ersetzen:
            self.pakete = list(neue)
        else:
            vorhanden = {os.path.normcase(e.pfad): i for i, e in enumerate(self.pakete)}
            for e in neue:
                schluessel = os.path.normcase(e.pfad)
                if schluessel in vorhanden:
                    self.pakete[vorhanden[schluessel]] = e
                else:
                    self.pakete.append(e)
        unlesbar = sum(1 for e in neue if not e.lesbar)
        self._log(self.t("ps4ota.log_scan_fertig", anzahl=len(neue), unlesbar=unlesbar))
        regionen = sorted({e.region for e in self.pakete if e.region})
        if self._region_box is not None:
            self._region_box.werte_setzen([self.t("ps4ota.alle")] + regionen)
        self._tabelle_neu()

    def _filter_loeschen(self) -> None:
        self.suche_var.set("")
        for var in (self.typ_var, self.region_var, self.echt_var):
            var.set(self.t("ps4ota.alle"))
        self.gruppe_var.set(self.t("ps4ota.gruppe_keine"))
        self._tabelle_neu()

    def _gefiltert(self) -> list[bib.PkgEintrag]:
        region = self.region_var.get()
        return bib.filtern(self.pakete, suche=self.suche_var.get(), typ=self._typ_namen.get(self.typ_var.get(), ""),
                           region="" if region == self.t("ps4ota.alle") else region,
                           echtheit=self._echt_namen.get(self.echt_var.get(), ""))

    def _sortieren(self, spalte: str) -> None:
        alt, absteigend = self._sortierung
        self._sortierung = (spalte, (not absteigend) if alt == spalte else False)
        self._tabelle_neu()

    def _sortschluessel(self, spalte: str) -> Callable[[bib.PkgEintrag], object]:
        if spalte in SORT_ZAHL:
            return SORT_ZAHL[spalte]
        if spalte == "typ":
            return lambda e: bib.TYPEN.index(e.typ) if e.typ in bib.TYPEN else 99
        feld = {"datei": "datei", "ordner": "ordner", "titel": "titel", "title_id": "title_id", "region": "region",
                "echtheit": "echtheit"}.get(spalte, "datei")
        return lambda e: (getattr(e, feld) or "").lower()

    def _zeile_werte(self, e: bib.PkgEintrag) -> tuple:
        t = self.t
        typ_text = {bib.TYP_BASIS: t("ps4ota.typ_base"), bib.TYP_UPDATE: t("ps4ota.typ_patch"),
                    bib.TYP_ZUSATZ: t("ps4ota.typ_addon"), bib.TYP_APP: t("ps4ota.typ_app")}.get(e.typ, t("ps4ota.typ_unbekannt"))
        echt_text = {bib.ECHT_FAKE: t("ps4ota.echt_fake"), bib.ECHT_OFFIZIELL: t("ps4ota.echt_official"),
                     bib.ECHT_OFFIZIELL_DP: t("ps4ota.echt_official_dp")}.get(e.echtheit, "")
        if not e.lesbar:
            return (e.datei, t("ps4ota.unlesbar", grund=e.fehler), "", "", "", "", "", self.g._fmt_bytes(e.groesse), "", "", e.ordner)
        return (e.datei, e.titel, e.title_id, typ_text, bib.ohne_fuehrende_nullen(e.app_ver), e.region, e.system_ver,
                self.g._fmt_bytes(e.groesse), echt_text, self._online.get(e.title_id, ""), e.ordner)

    def _zeilen_tags(self, e: bib.PkgEintrag) -> tuple:
        if not e.lesbar:
            return ("unlesbar",)
        tags = []
        if e.typ == bib.TYP_UPDATE:
            tags.append("update")
        elif e.typ == bib.TYP_ZUSATZ:
            tags.append("addon")
        online = self._online.get(e.title_id, "")
        if online and e.typ in (bib.TYP_BASIS, bib.TYP_UPDATE) and upd.ist_neuer(online, self._lokal_neueste(e.title_id)):
            tags.append("neuer")
        return tuple(tags)

    def _lokal_neueste(self, title_id: str) -> str:
        stand = ""
        for e in self.pakete:
            if e.lesbar and e.title_id == title_id and e.typ in (bib.TYP_BASIS, bib.TYP_UPDATE):
                if bib.fassung_zahlen(e.app_ver) > bib.fassung_zahlen(stand):
                    stand = e.app_ver
        return stand

    def _tabelle_neu(self) -> None:
        """Baut die Tabelle aus Filter, Sortierung und Gruppierung neu auf; die Auswahl bleibt, wo es geht."""
        gemerkt = {e.pfad for e in self._gewaehlt()}
        spalte, absteigend = self._sortierung
        sicht = sorted(self._gefiltert(), key=self._sortschluessel(spalte), reverse=absteigend)
        self.sicht = sicht
        self.baum.delete(*self.baum.get_children())
        self._iid_eintrag = {}
        gruppe = self._gruppen_namen.get(self.gruppe_var.get(), "")
        neu_gewaehlt = []
        if gruppe:
            for name, mitglieder in bib.gruppieren(sicht, gruppe):
                knoten = self.baum.insert("", "end", iid="g:" + name, open=True, tags=("gruppe",),
                                          values=("%s (%d)" % (name, len(mitglieder)),) + ("",) * (len(SPALTEN) - 1))
                for e in mitglieder:
                    iid = self._einfuegen(e, knoten)
                    if e.pfad in gemerkt:
                        neu_gewaehlt.append(iid)
        else:
            for e in sicht:
                iid = self._einfuegen(e, "")
                if e.pfad in gemerkt:
                    neu_gewaehlt.append(iid)
        if neu_gewaehlt:
            self.baum.selection_set(neu_gewaehlt)
        self.status_var.set(self.t("ps4ota.status_zaehler", gesamt=len(self.pakete), sichtbar=len(sicht),
                                   groesse=self.g._fmt_bytes(sum(e.groesse for e in sicht))))
        self._auswahl_geaendert()

    def _einfuegen(self, e: bib.PkgEintrag, eltern: str) -> str:
        iid = "p%d" % len(self._iid_eintrag)
        self.baum.insert(eltern, "end", iid=iid, values=self._zeile_werte(e), tags=self._zeilen_tags(e))
        self._iid_eintrag[iid] = e
        return iid

    def _gewaehlt(self) -> list[bib.PkgEintrag]:
        erg: list[bib.PkgEintrag] = []
        gesehen: set[str] = set()
        for iid in self.baum.selection():
            kandidaten = [iid]
            if iid.startswith("g:"):
                kandidaten = list(self.baum.get_children(iid))
            for k in kandidaten:
                e = self._iid_eintrag.get(k)
                if e is not None and e.pfad not in gesehen:
                    gesehen.add(e.pfad)
                    erg.append(e)
        return erg

    def _lesbare(self) -> list[bib.PkgEintrag]:
        return [e for e in self._gewaehlt() if e.lesbar]

    # ------------------------------------------------------------------
    # Auswahl und Einzelheiten
    # ------------------------------------------------------------------
    def _auswahl_geaendert(self, _e=None) -> None:
        if self._auswahl_zeitgeber is not None:
            try:
                self.win.after_cancel(self._auswahl_zeitgeber)
            except (tk.TclError, ValueError):
                pass
        self._auswahl_zeitgeber = self.win.after(120, self._auswahl_verarbeiten)

    def _auswahl_verarbeiten(self) -> None:
        self._auswahl_zeitgeber = None
        if self._schliesst or not self.win.winfo_exists():
            return
        gewaehlt = self._gewaehlt()
        n = len(gewaehlt)
        self.auswahl_var.set(self.t("ps4ota.auswahl_zaehler", anzahl=n) if n else "")
        self._aktionen_pruefen()
        if n >= 1 and gewaehlt[0].lesbar:
            if self._aktuell is None or self._aktuell.pfad != gewaehlt[0].pfad:
                self._details_zeigen(gewaehlt[0])
        elif n == 0:
            self._details_leeren()

    def _aktionen_pruefen(self) -> None:
        gewaehlt = self._gewaehlt()
        lesbar = [e for e in gewaehlt if e.lesbar]
        updates = [e for e in lesbar if e.typ == bib.TYP_UPDATE]
        basen = [e for e in lesbar if e.typ == bib.TYP_BASIS]
        frei = bs.freigeben
        frei(self.knoepfe["entpacken"], bool(lesbar))
        frei(self.knoepfe["ffpfsc"], bool(lesbar))
        frei(self.knoepfe["zusammen"], bool(updates) or (bool(basen) and len(lesbar) == 1))
        frei(self.knoepfe["neu_packen"], len(lesbar) == 1)
        frei(self.knoepfe["pruefen"], bool(lesbar))
        frei(self.knoepfe["umbenennen"], bool(self.pakete))
        frei(self.knoepfe["verschieben"], bool(self.pakete))
        frei(self.knoepfe["ota"], bool(lesbar))
        frei(self.update_nachsehen, len(lesbar) >= 1 and lesbar[0].typ in (bib.TYP_BASIS, bib.TYP_UPDATE))

    def _details_leeren(self) -> None:
        self._aktuell = None
        for knoten in self.info_baum.get_children():
            self.info_baum.delete(knoten)
        self.interna_baum.delete(*self.interna_baum.get_children())
        self.interna_kopf.set("")
        self._bilder.clear()
        self.icon_label.configure(image="", text="")
        for etikett in self._bild_labels.values():
            etikett.configure(image="", text="")
        self.dateien_baum.delete(*self.dateien_baum.get_children())
        self._dateien_eintraege = {}
        self._dateien_ist_datei = set()
        self._dateien_fuer = ""
        self.dateien_status.set(self.t("ps4ota.dateien_leer"))
        self._update_schreiben("")

    def _details_zeigen(self, e: bib.PkgEintrag) -> None:
        self._aktuell = e
        t = self.t
        self.info_baum.delete(*self.info_baum.get_children())
        zeilen = [(t("ps4ota.col_titel"), e.titel), (t("ps4ota.col_title_id"), e.title_id),
                  ("Content ID", e.content_id), (t("ps4ota.col_typ"), e.typ), (t("ps4ota.col_kategorie"), e.kategorie),
                  ("APP_VER", e.app_ver), ("VERSION", e.version), (t("ps4ota.col_region"), e.region),
                  (t("ps4ota.info_min_fw"), e.system_ver), (t("ps4ota.col_echtheit"), e.echtheit),
                  (t("ps4ota.info_paketgroesse"), self.g._fmt_bytes(e.paketgroesse) if e.paketgroesse else ""),
                  (t("ps4ota.col_groesse"), self.g._fmt_bytes(e.groesse)), (t("ps4ota.col_datei"), e.datei),
                  (t("ps4ota.col_ordner"), e.ordner)]
        self.info_baum.insert("", "end", values=(t("ps4ota.info_abschnitt_paket"), ""), tags=("abschnitt",))
        for feld, wert in zeilen:
            self.info_baum.insert("", "end", values=(feld, wert))
        self.info_baum.insert("", "end", values=("param.sfo", ""), tags=("abschnitt",))
        for schluessel in sorted(e.sfo):
            wert = e.sfo[schluessel]
            self.info_baum.insert("", "end", values=(schluessel, "0x%08X" % wert if isinstance(wert, int) else wert))
        self._interna_zeigen(e)
        self._bilder_laden(e)
        self._dateien_zuruecksetzen(e)
        self._update_zeigen(e)
        if self._aktuelle_seite() == "dateien":
            self._dateien_laden()

    def _interna_zeigen(self, e: bib.PkgEintrag) -> None:
        self.interna_baum.delete(*self.interna_baum.get_children())
        eintraege = bib.lese_eintragsliste(e.pfad)
        self.interna_kopf.set("Content ID  %s\n%s  %s\n%s  %d" % (
            e.content_id, self.t("ps4ota.info_paketgroesse"), self.g._fmt_bytes(e.paketgroesse) if e.paketgroesse else "-",
            self.t("ps4ota.interna_anzahl"), len(eintraege)))
        for r in eintraege:
            self.interna_baum.insert("", "end", values=(
                "0x%04X" % r["kennung"], r["name"], r["groesse"], "0x%X" % r["offset"],
                self.t("ps4ota.ja") if r["verschluesselt"] else self.t("ps4ota.nein")))

    # -- Bilder ------------------------------------------------------------------
    def _bilder_laden(self, e: bib.PkgEintrag) -> None:
        pfad = e.pfad
        self._bilder.clear()

        def arbeit() -> None:
            erg = {}
            for kennung in (bib.EINTRAG_ICON0, bib.EINTRAG_PIC0, bib.EINTRAG_PIC1):
                erg[kennung] = bib.lese_bild(pfad, kennung)
            self._z["bilder"] = (pfad, erg)

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-bilder").start()

    def _bilder_zeigen(self, pfad: str, daten: dict) -> None:
        if self._aktuell is None or self._aktuell.pfad != pfad:
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:   # pragma: no cover - PIL gehoert zu den Abhaengigkeiten
            return
        for schluessel, kennung, grenze in (("icon0", bib.EINTRAG_ICON0, (140, 140)), ("pic0", bib.EINTRAG_PIC0, (300, 170)),
                                            ("pic1", bib.EINTRAG_PIC1, (300, 170))):
            roh = daten.get(kennung)
            etikett = self._bild_labels[schluessel]
            if not roh:
                etikett.configure(image="", text=self.t("ps4ota.bild_keins"), fg=self.c["fg_secondary"])
                if schluessel == "icon0":
                    self.icon_label.configure(image="", text=self.t("ps4ota.bild_keins"), fg=self.c["fg_secondary"])
                continue
            try:
                bild = Image.open(io.BytesIO(roh))
                bild.load()
                bild.thumbnail(grenze)
                foto = ImageTk.PhotoImage(bild)
            except Exception:  # noqa: BLE001
                etikett.configure(image="", text=self.t("ps4ota.bild_fehler"))
                continue
            self._bilder[schluessel] = foto
            etikett.configure(image=foto, text="", width=foto.width(), height=foto.height())
            if schluessel == "icon0":
                self.icon_label.configure(image=foto, text="", width=foto.width(), height=foto.height())

    def _bild_speichern(self, kennung: int, schluessel: str) -> None:
        e = self._aktuell
        if e is None:
            return
        roh = bib.lese_bild(e.pfad, kennung)
        if not roh:
            self._fehler("ps4ota.bild_keins_speichern")
            return
        ziel = filedialog.asksaveasfilename(title=self.t("ps4ota.bild_speichern"), defaultextension=".png",
                                            initialfile="%s_%s.png" % (e.title_id or "pkg", schluessel),
                                            filetypes=[("PNG", "*.png")], parent=self.win)
        if not ziel:
            return
        try:
            with open(ziel, "wb") as f:
                f.write(roh)
            self._log(self.t("ps4ota.log_bild_gespeichert", pfad=ziel))
        except OSError as fehler:
            messagebox.showerror(self.t("ps4ota.window_title"), str(fehler), parent=self.win)

    # -- Dateien -------------------------------------------------------------------
    def _dateien_zuruecksetzen(self, e: bib.PkgEintrag) -> None:
        self.dateien_baum.delete(*self.dateien_baum.get_children())
        self._dateien_eintraege = {}
        self._dateien_ist_datei = set()
        self._dateien_fuer = ""
        self.dateien_status.set(self.t("ps4ota.dateien_leer"))
        self._z.pop("dateien", None)

    def _dateien_laden(self, erzwingen: bool = False) -> None:
        e = self._aktuell
        if e is None:
            return
        if not erzwingen and self._dateien_fuer == e.pfad:
            return
        if not self._werkzeug_da_still():
            self.dateien_status.set(self.t("ps4ota.dateien_ohne_werkzeug"))
            return
        self._dateien_fuer = e.pfad
        self.dateien_status.set(self.t("ps4ota.dateien_lade"))
        pfad = e.pfad

        def arbeit() -> None:
            try:
                self._z["dateien"] = (pfad, orbispkg.liste(pfad), "")
            except orbispkg.OrbisFehler as fehler:
                self._z["dateien"] = (pfad, None, str(fehler))

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-dateien").start()

    def _werkzeug_da_still(self) -> bool:
        return orbispkg.verfuegbar()

    def _dateien_zeigen(self, pfad: str, eintraege, fehler: str) -> None:
        if self._aktuell is None or self._aktuell.pfad != pfad:
            return
        self.dateien_baum.delete(*self.dateien_baum.get_children())
        self._dateien_eintraege = {}
        self._dateien_ist_datei = set()
        if eintraege is None:
            self.dateien_status.set(self.t("ps4ota.dateien_fehler", fehler=fehler))
            return
        knoten: dict[str, str] = {}
        dateien = 0
        for eintrag in sorted(eintraege, key=lambda x: x.pfad.lower()):
            teile = eintrag.pfad.split("/")
            eltern = ""
            for tiefe in range(len(teile) - 1):
                teil_pfad = "/".join(teile[:tiefe + 1])
                if teil_pfad not in knoten:
                    knoten[teil_pfad] = self.dateien_baum.insert(
                        knoten.get("/".join(teile[:tiefe])) or "", "end", text=teile[tiefe], open=tiefe == 0)
                    self._dateien_eintraege[knoten[teil_pfad]] = teil_pfad
                eltern = knoten[teil_pfad]
            if eintrag.ist_ordner:
                if eintrag.pfad not in knoten:
                    knoten[eintrag.pfad] = self.dateien_baum.insert(eltern, "end", text=teile[-1], open=len(teile) == 1)
                    self._dateien_eintraege[knoten[eintrag.pfad]] = eintrag.pfad
            else:
                iid = self.dateien_baum.insert(eltern, "end", text=teile[-1],
                                               values=(self.g._fmt_bytes(eintrag.groesse),))
                self._dateien_eintraege[iid] = eintrag.pfad
                self._dateien_ist_datei.add(iid)
                dateien += 1
        self.dateien_status.set(self.t("ps4ota.dateien_anzahl", anzahl=dateien))

    def _dateien_auswahl_pfade(self) -> list[str]:
        """Die gewaehlten Dateien im Paket; ein gewaehlter Ordner steht fuer alle Dateien darunter."""
        pfade: list[str] = []
        for iid in self.dateien_baum.selection():
            kinder = [iid]
            stapel = list(self.dateien_baum.get_children(iid))
            while stapel:
                k = stapel.pop()
                kinder.append(k)
                stapel.extend(self.dateien_baum.get_children(k))
            for k in kinder:
                p = self._dateien_eintraege.get(k, "")
                if p and k in self._dateien_ist_datei and p not in pfade:
                    pfade.append(p)
        return sorted(pfade, key=str.lower)

    def _dateien_auswahl_entpacken(self) -> None:
        e = self._aktuell
        if e is None or not self._werkzeug_da():
            return
        pfade = self._dateien_auswahl_pfade()
        if not pfade:
            self._fehler("ps4ota.dateien_nichts_gewaehlt")
            return
        ziel = filedialog.askdirectory(title=self.t("ps4ota.dlg_ziel_waehlen"),
                                       initialdir=str(self._einstellung(EINST_ZIEL, "") or "") or None, parent=self.win)
        if not ziel:
            return
        self._merken(EINST_ZIEL, ziel)
        ziel = os.path.normpath(ziel)

        def arbeit(a: au.Aufgabe) -> None:
            fertig = 0
            for nr, eintrag in enumerate(pfade, 1):
                a.pruefen_abbruch()
                a.melden(self.t("ps4ota.status_einzeln", aktuell=nr, gesamt=len(pfade), datei=eintrag), 100.0 * nr / len(pfade))
                lauf = orbispkg.entpacken_eintrag(e.pfad, eintrag, ziel, abbruch=lambda: a.abbruch_verlangt,
                                                  prozess_ablage=a.prozess_ablage)
                a.pruefen_abbruch()
                if lauf.rueckgabe != 0:
                    raise au.AufgabeFehler("werkzeug", lauf.letzte_fehlerzeile, grund=lauf.letzte_fehlerzeile)
                fertig += 1
            a.ergebnis = ziel
            a.melden(self.t("ps4ota.status_einzeln_fertig", anzahl=fertig), 100)

        self._aufgabe_hinzufuegen("einzeln", self.t("ps4ota.aufg_titel_einzeln", datei=e.datei, anzahl=len(pfade)),
                                  arbeit, quelle=e.pfad, ziel=ziel)

    def _dateien_exportieren(self) -> None:
        if not self._dateien_eintraege:
            self._fehler("ps4ota.dateien_nichts_zu_exportieren")
            return
        ziel = filedialog.asksaveasfilename(title=self.t("ps4ota.dateien_exportieren"), defaultextension=".txt",
                                            initialfile="%s_dateien.txt" % (self._aktuell.title_id if self._aktuell else "pkg"),
                                            filetypes=[("Text", "*.txt")], parent=self.win)
        if not ziel:
            return
        try:
            with open(ziel, "w", encoding="utf-8") as f:
                for iid, pfad in sorted(self._dateien_eintraege.items(), key=lambda kv: kv[1].lower()):
                    if not self.dateien_baum.get_children(iid):
                        f.write("%s\t%s\n" % (pfad, self.dateien_baum.set(iid, "groesse")))
            self._log(self.t("ps4ota.log_liste_exportiert", pfad=ziel))
        except OSError as fehler:
            messagebox.showerror(self.t("ps4ota.window_title"), str(fehler), parent=self.win)

    # -- Update -------------------------------------------------------------------------
    def _update_zeigen(self, e: bib.PkgEintrag) -> None:
        t = self.t
        neuestes = bib.neuestes_update(self.pakete, e.title_id)
        basis = bib.passendes_basisspiel(self.pakete, neuestes or e)
        zeilen = [t("ps4ota.update_titel", titel=e.titel, title_id=e.title_id)]
        zeilen.append(t("ps4ota.update_lokal_basis", datei=basis.datei if basis else "-"))
        zeilen.append(t("ps4ota.update_lokal_neuestes", version=neuestes.app_ver if neuestes else "-"))
        info = self._update_info.get(e.title_id)
        if info is not None:
            zeilen.append("")
            zeilen.append(self._update_info_text(info, neuestes.app_ver if neuestes else (e.app_ver if e.typ == bib.TYP_BASIS else "")))
        self._update_schreiben("\n".join(zeilen))
        bs.freigeben(self.update_laden, info is not None and info.verzeichnis is not None)

    def _update_info_text(self, info: upd.UpdateInfo, lokal: str) -> str:
        t = self.t
        zeilen = [t("ps4ota.update_online_version", version=info.version or "-"),
                  t("ps4ota.update_online_groesse", groesse=self.g._fmt_bytes(info.groesse) if info.groesse else "-"),
                  t("ps4ota.update_online_system", system=info.system_ver or "-"),
                  t("ps4ota.update_online_pflicht", pflicht=t("ps4ota.ja") if info.pflicht else t("ps4ota.nein")),
                  t("ps4ota.update_online_teile", anzahl=len(info.verzeichnis.teile) if info.verzeichnis else 0)]
        if info.version and upd.ist_neuer(info.version, lokal):
            zeilen.append(t("ps4ota.update_neuer"))
        elif info.version:
            zeilen.append(t("ps4ota.update_aktuell"))
        return "\n".join(zeilen)

    def _aktion_update_online(self) -> None:
        lesbar = self._lesbare()
        if not lesbar:
            return
        e = lesbar[0]
        if not upd.title_id_gueltig(e.title_id):
            self._fehler("ps4ota.update_keine_title_id")
            return
        self._update_schreiben(self.t("ps4ota.update_frage", title_id=e.title_id))
        bs.freigeben(self.update_nachsehen, False)
        title_id = e.title_id

        def arbeit() -> None:
            try:
                self._z["update_ergebnis"] = (title_id, upd.nachsehen(title_id), "")
            except upd.UpdateFehler as fehler:
                self._z["update_ergebnis"] = (title_id, None, fehler.schluessel + ": " + fehler.text)
            except ValueError as fehler:
                self._z["update_ergebnis"] = (title_id, None, str(fehler))

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-update").start()

    def _update_ergebnis(self, title_id: str, info, fehler: str) -> None:
        bs.freigeben(self.update_nachsehen, True)
        if fehler:
            self._update_schreiben(self.t("ps4ota.update_fehler", fehler=fehler))
            self._log(self.t("ps4ota.log_update_fehler", title_id=title_id, fehler=fehler))
            return
        if info is None:
            self._online[title_id] = ""
            self._update_schreiben(self.t("ps4ota.update_keins", title_id=title_id))
            self._log(self.t("ps4ota.log_update_keins", title_id=title_id))
            return
        self._update_info[title_id] = info
        self._online[title_id] = info.version
        self._log(self.t("ps4ota.log_update_gefunden", title_id=title_id, version=info.version))
        self._tabelle_neu()
        if self._aktuell is not None and self._aktuell.title_id == title_id:
            self._update_zeigen(self._aktuell)

    def _aktion_update_laden(self) -> None:
        e = self._aktuell
        if e is None:
            return
        info = self._update_info.get(e.title_id)
        if info is None or info.verzeichnis is None or not info.verzeichnis.teile:
            self._fehler("ps4ota.update_ohne_teile")
            return
        if not messagebox.askyesno(self.t("ps4ota.window_title"),
                                   self.t("ps4ota.update_laden_frage", version=info.version,
                                          groesse=self.g._fmt_bytes(info.groesse or info.verzeichnis.gesamtgroesse)),
                                   parent=self.win):
            return
        ziel = filedialog.askdirectory(title=self.t("ps4ota.dlg_ziel_waehlen"), initialdir=e.ordner or None, parent=self.win)
        if not ziel:
            return
        ziel = os.path.normpath(ziel)
        self._aufgabe_hinzufuegen("update", self.t("ps4ota.aufg_titel_update", title_id=e.title_id, version=info.version),
                                  lambda a: au.arbeit_update_laden(a, info, ziel, self.t), quelle=e.title_id, ziel=ziel)

    def _aktion_alle_online(self) -> None:
        ids = sorted({e.title_id for e in self.pakete if e.lesbar and e.typ in (bib.TYP_BASIS, bib.TYP_UPDATE)
                      and upd.title_id_gueltig(e.title_id)})
        if not ids:
            self._fehler("ps4ota.update_keine_titel")
            return
        if self._z.get("online_laeuft"):
            return
        self._z.update(online_laeuft=True, online_abbruch=False)
        bs.freigeben(self.update_alle, False)
        self._log(self.t("ps4ota.log_update_alle_start", anzahl=len(ids)))

        def arbeit() -> None:
            ergebnisse: dict[str, str] = {}
            fehler = ""
            try:
                for nr, title_id in enumerate(ids, 1):
                    if self._z.get("online_abbruch"):
                        break
                    self._z["online_text"] = (nr, len(ids), title_id)
                    try:
                        info = upd.nachsehen(title_id)
                        ergebnisse[title_id] = info.version if info else ""
                    except upd.UpdateFehler as f:
                        if f.schluessel == "netz":
                            fehler = f.text
                            break
                        ergebnisse[title_id] = ""
                    time.sleep(0.15)
            finally:
                self._z["online_ergebnis"] = (ergebnisse, fehler)
                self._z["online_laeuft"] = False

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-update-alle").start()

    # ------------------------------------------------------------------
    # Aktionen
    # ------------------------------------------------------------------
    def _aufgabe_hinzufuegen(self, art: str, titel: str, arbeit, *, quelle: str = "", ziel: str = "") -> au.Aufgabe:
        aufgabe = self.warteschlange.hinzufuegen(art, titel, arbeit, quelle=quelle, ziel=ziel)
        self._log(self.t("ps4ota.log_aufgabe_neu", titel=titel))
        self._notizbuch_waehlen("aufgaben")
        # Gleich zeigen: Bis der Takt (150 ms) kaeme, saehe der Anwender eine leere Liste.
        self._aufgaben_anzeigen()
        return aufgabe

    def _aktion_entpacken(self) -> None:
        pakete = self._lesbare()
        if not pakete:
            return
        if not orbispkg.verfuegbar():
            # Es gibt OrbisPkgTool nur fuer Windows. Wo es fehlt (Linux, macOS), bleibt der bisherige
            # Entpacker des PS4 FFPFSC - sonst verloere dort jemand, was bisher ging.
            self._bisheriger_entpacker()
            return
        if not self._werkzeug_da():
            return
        vorgaben = {"ziel": str(self._einstellung(EINST_ZIEL, "") or ""), "dump_form": True}
        antwort = dlg.frage_entpacken(self.g, self.win, pakete, vorgaben, self.F, self.pt)
        if not antwort:
            return
        self._merken(EINST_ZIEL, antwort["ziel"])
        for e in pakete:
            ziel = os.path.join(antwort["ziel"], au.zielordner_name(e))
            self._aufgabe_hinzufuegen(
                "entpacken", self.t("ps4ota.aufg_titel_entpacken", datei=e.datei),
                lambda a, e=e, ziel=ziel: self._entpacken_und_oeffnen(a, e, ziel, antwort),
                quelle=e.pfad, ziel=ziel)

    def _bisheriger_entpacker(self) -> None:
        """Das Fenster „PS4 PKG -> Dump Ordner“ (``ps4_pkg_extract`` des PS4 FFPFSC) - fragt selbst nach der Datei."""
        oeffnen = getattr(self.g, "_show_pkg_entpacken", None)
        if callable(oeffnen):
            oeffnen()
        else:
            self._werkzeug_da()

    def _paketkopf_lesen(self) -> None:
        """Der bisherige Leser fuer den aeusseren Container eines Pakets (PS4 und PS5, ProsperoPkg)."""
        self.g._show_pkg_reader()

    def _entpacken_und_oeffnen(self, a: au.Aufgabe, e: bib.PkgEintrag, ziel: str, antwort: dict) -> None:
        au.arbeit_entpacken(a, e.pfad, ziel, self.t, dump_form=antwort["dump_form"], passcode=antwort["passcode"])
        if antwort.get("oeffnen"):
            self._z.setdefault("oeffnen", []).append(ziel)

    def _aktion_ffpfsc(self) -> None:
        pakete = self._lesbare()
        if not pakete:
            return
        self.g._ps4pkg_vorgabe = os.pathsep.join(e.pfad for e in pakete)
        self.g._show_ps4_pkg_converter()

    def _aktion_zusammenfuehren(self) -> None:
        if not self._werkzeug_da():
            return
        lesbar = self._lesbare()
        updates = [e for e in lesbar if e.typ == bib.TYP_UPDATE]
        basen = [e for e in lesbar if e.typ == bib.TYP_BASIS]
        update = None
        basis = None
        if updates:
            update = max(updates, key=lambda e: bib.fassung_zahlen(e.app_ver))
            basis = next((b for b in basen if b.title_id == update.title_id), None) or \
                bib.passendes_basisspiel(self.pakete, update)
        elif basen and len(lesbar) == 1:
            basis = basen[0]
            update = bib.neuestes_update(self.pakete, basis.title_id)
        if basis is None or update is None:
            self._fehler("ps4ota.zusammen_unvollstaendig")
            return
        antwort = dlg.frage_zusammenfuehren(self.g, self.win, basis, update, {"ordner": basis.ordner}, self.F, self.pt)
        if not antwort:
            return
        self._aufgabe_hinzufuegen(
            "zusammen", self.t("ps4ota.aufg_titel_zusammen", titel=basis.titel or basis.title_id, version=update.app_ver),
            lambda a: au.arbeit_zusammenfuehren(a, basis.pfad, update.pfad, antwort["ausgabe"], self.t,
                                               pruefen_danach=antwort["pruefen"], pfsc_modus=antwort["modus"],
                                               arbeiter=antwort["arbeiter"]),
            quelle=basis.pfad, ziel=antwort["ausgabe"])

    def _aktion_neu_packen(self) -> None:
        lesbar = self._lesbare()
        if len(lesbar) != 1 or not self._werkzeug_da():
            return
        e = lesbar[0]
        antwort = dlg.frage_neu_packen(self.g, self.win, e, {}, self.F, self.pt)
        if not antwort:
            return
        self._aufgabe_hinzufuegen(
            "neu_packen", self.t("ps4ota.aufg_titel_neu_packen", datei=e.datei),
            lambda a: au.arbeit_neu_packen(a, e.pfad, antwort["ausgabe"], self.t, pruefen_danach=antwort["pruefen"],
                                           pfsc_modus=antwort["modus"], arbeiter=antwort["arbeiter"]),
            quelle=e.pfad, ziel=antwort["ausgabe"])

    def _aktion_pruefen(self, tief: bool = False) -> None:
        pakete = self._lesbare()
        if not pakete or not self._werkzeug_da():
            return
        for e in pakete:
            self._aufgabe_hinzufuegen("pruefen", self.t("ps4ota.aufg_titel_pruefen", datei=e.datei),
                                      lambda a, e=e: au.arbeit_pruefen(a, e.pfad, self.t, tief=tief), quelle=e.pfad)

    def _aktion_bauen(self) -> None:
        if not self._werkzeug_da():
            return
        antwort = dlg.frage_bauen(self.g, self.win, {}, self.F, self.pt)
        if not antwort:
            return
        self._aufgabe_hinzufuegen(
            "bauen", self.t("ps4ota.aufg_titel_bauen", ordner=os.path.basename(antwort["quelle"].rstrip("\\/"))),
            lambda a: au.arbeit_bauen(a, antwort["quelle"], antwort["ausgabe"], self.t, patch=antwort["patch"],
                                      pruefen_danach=antwort["pruefen"], pfsc_modus=antwort["modus"],
                                      arbeiter=antwort["arbeiter"]),
            quelle=antwort["quelle"], ziel=antwort["ausgabe"])

    def _plan_ausfuehren(self, plan: list[bib.Umbenennung]) -> None:
        """Fuehrt einen Umbenennen-/Verschieben-Plan aus und zieht die Eintraege nach."""
        neu = {os.path.normcase(s.quelle): s.ziel for s in plan}
        fehler = bib.plan_ausfuehren(plan)
        gescheitert = {os.path.normcase(s.quelle): grund for s, grund in fehler}
        for e in self.pakete:
            schluessel = os.path.normcase(e.pfad)
            if schluessel in neu and schluessel not in gescheitert:
                e.pfad = os.path.normpath(neu[schluessel])
        self._log(self.t("ps4ota.log_plan_fertig", gesamt=len(plan), fehler=len(fehler)))
        for schritt, grund in fehler:
            self._log(self.t("ps4ota.log_plan_fehler", datei=os.path.basename(schritt.quelle), grund=grund))
        if fehler:
            messagebox.showwarning(self.t("ps4ota.window_title"),
                                   self.t("ps4ota.plan_fehler", anzahl=len(fehler), erster=fehler[0][1]), parent=self.win)
        self._merken_quellen_nach_plan()
        self._tabelle_neu()

    def _merken_quellen_nach_plan(self) -> None:
        """Nach dem Verschieben bleiben die gemerkten Quellen gueltig: Ihre Ordner gibt es weiter."""
        return

    def _aktion_umbenennen(self) -> None:
        pakete = self._gewaehlt() or list(self.sicht)
        pakete = [e for e in pakete if e.lesbar]
        if not pakete:
            return
        t = self.t
        optionen = [("v%d" % nr, "%d  %s" % (nr, vorlage.replace("{", "").replace("}", ""))) for nr, vorlage in bib.VORLAGEN]
        optionen += [("eigen", t("ps4ota.vorlage_eigen")), ("prio", t("ps4ota.vorlage_prioritaet"))]
        vorlagen = {"v%d" % nr: vorlage for nr, vorlage in bib.VORLAGEN}

        def plan(kennung: str, eingabe: str) -> list[bib.Umbenennung]:
            if kennung == "prio":
                return bib.install_prioritaet_plan(pakete)
            vorlage = eingabe if kennung == "eigen" else vorlagen.get(kennung, "{TITLE}")
            if kennung == "eigen" and not bib.vorlage_gueltig(vorlage)[0]:
                return []
            return bib.umbenennen_plan(pakete, vorlage)

        antwort = dlg.frage_vorschau(self.g, self.win, t("ps4ota.umbenennen_titel"),
                                     t("ps4ota.umbenennen_untertitel", anzahl=len(pakete)), optionen, plan, self.F, self.pt,
                                     eigene_eingabe=True, eingabe_text="{TITLE} [{TITLE_ID}] [{APP_VERSION}]",
                                     feld_titel=t("ps4ota.vorlage_eigen_feld"))
        if antwort and antwort.get("plan"):
            self._plan_ausfuehren(antwort["plan"])

    def _aktion_verschieben(self) -> None:
        pakete = [e for e in (self._gewaehlt() or list(self.sicht)) if e.lesbar]
        if not pakete:
            return
        t = self.t
        optionen = [("titel", t("ps4ota.verschieben_titel_art")), ("title_id", t("ps4ota.verschieben_title_id")),
                    ("kategorie", t("ps4ota.verschieben_kategorie")), ("echtheit", t("ps4ota.verschieben_echtheit")),
                    ("region", t("ps4ota.verschieben_region")), ("einzelordner", t("ps4ota.verschieben_einzel"))]
        basis = pakete[0].ordner

        def plan(kennung: str, ziel: str) -> list[bib.Umbenennung]:
            if not ziel:
                return []
            return bib.verschieben_plan(pakete, kennung, ziel, einzelordner="PKG")

        antwort = dlg.frage_vorschau(self.g, self.win, t("ps4ota.verschieben_fenster"),
                                     t("ps4ota.verschieben_untertitel", anzahl=len(pakete)), optionen, plan, self.F, self.pt,
                                     basis_ordner=basis, mit_ordnerwahl=True)
        if antwort and antwort.get("plan"):
            self._plan_ausfuehren(antwort["plan"])

    # -- Mehr-Menue --------------------------------------------------------
    def _mehr_menue(self, knopf) -> None:
        t = self.t
        menue = self._menue()
        menue.add_command(label=t("ps4ota.mehr_bauen"), command=self._aktion_bauen)
        menue.add_command(label=t("ps4ota.mehr_tiefpruefung"), command=lambda: self._aktion_pruefen(tief=True))
        menue.add_separator()
        menue.add_command(label=t("ps4ota.mehr_duplikate"), command=self._pruefung_duplikate)
        menue.add_command(label=t("ps4ota.mehr_ohne_basis"), command=self._pruefung_ohne_basis)
        menue.add_separator()
        menue.add_command(label=t("ps4ota.mehr_exportieren"), command=self._liste_exportieren)
        menue.add_command(label=t("ps4ota.mehr_im_ordner"), command=self._im_ordner_zeigen)
        menue.add_command(label=t("ps4ota.mehr_entfernen"), command=self._aus_liste_entfernen)
        menue.add_separator()
        menue.add_command(label=t("ps4ota.mehr_container_lesen"), command=self._paketkopf_lesen)
        menue.add_separator()
        kopieren = tk.Menu(menue, tearoff=0, bg=self.c["bg_card"], fg=self.c["fg_primary"],
                           activebackground=self.c["fg_accent"], activeforeground=self.c["bg_main"],
                           font=(self.F, self.pt(9)))
        for feld, text in (("title_id", "ps4ota.col_title_id"), ("content_id", "ps4ota.kopieren_content_id"),
                           ("titel", "ps4ota.col_titel"), ("datei", "ps4ota.col_datei")):
            kopieren.add_command(label=t(text), command=lambda f=feld: self._kopieren(f))
        menue.add_cascade(label=t("ps4ota.mehr_kopieren"), menu=kopieren)
        x = knopf.winfo_rootx()
        y = knopf.winfo_rooty() + knopf.winfo_height()
        try:
            menue.tk_popup(x, y)
        finally:
            menue.grab_release()

    def _kontextmenue(self, ereignis) -> None:
        iid = self.baum.identify_row(ereignis.y)
        if iid and iid not in self.baum.selection():
            self.baum.selection_set(iid)
        t = self.t
        menue = self._menue()
        for text, befehl in (("ps4ota.btn_entpacken", self._aktion_entpacken), ("ps4ota.btn_zusammen", self._aktion_zusammenfuehren),
                             ("ps4ota.btn_pruefen", self._aktion_pruefen), ("ps4ota.btn_ota", self._aktion_ota_senden)):
            menue.add_command(label=t(text), command=befehl)
        menue.add_separator()
        menue.add_command(label=t("ps4ota.mehr_im_ordner"), command=self._im_ordner_zeigen)
        menue.add_command(label=t("ps4ota.mehr_entfernen"), command=self._aus_liste_entfernen)
        try:
            menue.tk_popup(ereignis.x_root, ereignis.y_root)
        finally:
            menue.grab_release()

    def _info_menue(self, ereignis) -> None:
        iid = self.info_baum.identify_row(ereignis.y)
        if not iid:
            return
        self.info_baum.selection_set(iid)
        menue = self._menue()
        menue.add_command(label=self.t("ps4ota.wert_kopieren"),
                          command=lambda: self._in_zwischenablage(self.info_baum.set(iid, "wert")))
        try:
            menue.tk_popup(ereignis.x_root, ereignis.y_root)
        finally:
            menue.grab_release()

    def _in_zwischenablage(self, text: str) -> None:
        self.win.clipboard_clear()
        self.win.clipboard_append(text)

    def _kopieren(self, feld: str) -> None:
        werte = [str(getattr(e, feld, "") or "") for e in self._gewaehlt()]
        if werte:
            self._in_zwischenablage("\n".join(werte))

    def _im_ordner_zeigen(self) -> None:
        gewaehlt = self._gewaehlt()
        if gewaehlt:
            self.g._oeffnen_oder_melden(gewaehlt[0].ordner, self.t("ps4ota.window_title"), parent=self.win)

    def _aus_liste_entfernen(self) -> None:
        weg = {os.path.normcase(e.pfad) for e in self._gewaehlt()}
        if not weg:
            return
        self.pakete = [e for e in self.pakete if os.path.normcase(e.pfad) not in weg]
        self._tabelle_neu()

    def _liste_exportieren(self) -> None:
        eintraege = self._gewaehlt() or list(self.sicht)
        if not eintraege:
            return
        ziel = filedialog.asksaveasfilename(title=self.t("ps4ota.mehr_exportieren"), defaultextension=".csv",
                                            initialfile="ps4_pkg_liste.csv", filetypes=[("CSV", "*.csv")], parent=self.win)
        if not ziel:
            return
        try:
            n = bib.als_csv(eintraege, ziel)
            self._log(self.t("ps4ota.log_liste_exportiert_n", pfad=ziel, anzahl=n))
        except OSError as fehler:
            messagebox.showerror(self.t("ps4ota.window_title"), str(fehler), parent=self.win)

    def _pruefung_duplikate(self) -> None:
        gruppen = bib.duplikate(self.pakete)
        if not gruppen:
            messagebox.showinfo(self.t("ps4ota.window_title"), self.t("ps4ota.duplikate_keine"), parent=self.win)
            return
        zeilen = []
        for gruppe in gruppen[:12]:
            zeilen.append("%s [%s] %s" % (gruppe[0].titel, gruppe[0].title_id, gruppe[0].app_ver))
            zeilen.extend("    " + e.pfad for e in gruppe)
        self._log(self.t("ps4ota.log_duplikate", anzahl=len(gruppen)))
        messagebox.showinfo(self.t("ps4ota.window_title"),
                            self.t("ps4ota.duplikate_gefunden", anzahl=len(gruppen), liste="\n".join(zeilen)), parent=self.win)

    def _pruefung_ohne_basis(self) -> None:
        lose = bib.patches_ohne_basis(self.pakete)
        if not lose:
            messagebox.showinfo(self.t("ps4ota.window_title"), self.t("ps4ota.ohne_basis_keine"), parent=self.win)
            return
        self._log(self.t("ps4ota.log_ohne_basis", anzahl=len(lose)))
        messagebox.showinfo(self.t("ps4ota.window_title"),
                            self.t("ps4ota.ohne_basis_gefunden", anzahl=len(lose),
                                   liste="\n".join("%s [%s] %s" % (e.titel, e.title_id, e.app_ver) for e in lose[:15])),
                            parent=self.win)

    # ------------------------------------------------------------------
    # OTA
    # ------------------------------------------------------------------
    def _ota_ziel(self) -> "tuple[str, int] | None":
        ip = self.ota_ip_var.get().strip()
        if not ota.adresse_gueltig(ip):
            self._fehler("ps4ota.ota_ip_ungueltig")
            return None
        try:
            port = int(self.ota_port_var.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError(port)
        except ValueError:
            self._fehler("ps4ota.ota_port_ungueltig")
            return None
        self._merken(EINST_IP, ip)
        self._merken(EINST_PORT, port)
        return ip, port

    def _ota_erkennen(self) -> None:
        ziel = self._ota_ziel()
        if ziel is None:
            return
        self.ota_erkannt.set(self.t("ps4ota.ota_erkenne"))
        ip, port = ziel

        def arbeit() -> None:
            self._z["ota_erkannt"] = ota.erkennen(ip, port)

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-erkennen").start()

    def _ota_erkannt_zeigen(self, art: str) -> None:
        t = self.t
        if art == ota.ART_DPI_API:
            self.ota_art_var.set(ART_DPI)
            self.ota_erkannt.set(t("ps4ota.ota_erkannt_dpi"))
        elif art == ota.ART_DPI_WEB:
            self.ota_art_var.set(ART_DPI)
            self.ota_erkannt.set(t("ps4ota.ota_erkannt_dpi_web"))
        elif art == ota.ART_RPI:
            self.ota_art_var.set(ART_RPI)
            self.ota_erkannt.set(t("ps4ota.ota_erkannt_rpi"))
        else:
            self.ota_erkannt.set(t("ps4ota.ota_nichts"))
        self._ota_art_geaendert()

    def _aktion_ota_senden(self) -> None:
        pakete = self._lesbare()
        if not pakete:
            return
        ziel = self._ota_ziel()
        if ziel is None:
            self._notizbuch_waehlen("ota")
            return
        ip, port = ziel
        art = self.ota_art_var.get()
        t = self.t
        gesamt = sum(e.groesse for e in pakete)
        if not messagebox.askyesno(t("ps4ota.window_title"),
                                   t("ps4ota.ota_frage", anzahl=len(pakete), groesse=self.g._fmt_bytes(gesamt), ip=ip,
                                     art=t("ps4ota.ota_art_dpi") if art == ART_DPI else t("ps4ota.ota_art_rpi")),
                                   parent=self.win):
            return
        if art == ART_DPI:
            for e in pakete:
                self._aufgabe_hinzufuegen("ota", t("ps4ota.aufg_titel_ota", datei=e.datei, ip=ip),
                                          lambda a, pfad=e.pfad: au.arbeit_ota_dpi(a, pfad, ip, port, t),
                                          quelle=e.pfad, ziel=ip)
        else:
            pc = self.ota_pc_var.get().strip()
            eigene = "" if (not pc or pc == t("ps4ota.ota_pc_auto")) else pc
            try:
                server_port = max(0, int(self.ota_serverport_var.get().strip() or "0"))
            except ValueError:
                server_port = 0
            pfade = [e.pfad for e in pakete]
            self._aufgabe_hinzufuegen("ota", t("ps4ota.aufg_titel_ota_rpi", anzahl=len(pfade), ip=ip),
                                      lambda a: au.arbeit_ota_rpi(a, pfade, ip, port, t, eigene_ip=eigene,
                                                                  server_port=server_port),
                                      quelle=pfade[0], ziel=ip)

    def _ota_installiert(self) -> None:
        ziel = self._ota_ziel()
        lesbar = self._lesbare()
        if ziel is None or not lesbar:
            return
        ip, port = ziel
        title_id = lesbar[0].title_id
        self.ota_status_var.set(self.t("ps4ota.ota_frage_laeuft"))

        def arbeit() -> None:
            try:
                self._z["ota_kurz"] = ("installiert", title_id, ota.RpiClient(ip, port).ist_installiert(title_id), "")
            except ota.OtaFehler as fehler:
                self._z["ota_kurz"] = ("installiert", title_id, False, str(fehler.text or fehler.schluessel))

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-installiert").start()

    def _ota_deinstallieren_menue(self, knopf) -> None:
        lesbar = self._lesbare()
        if not lesbar:
            return
        e = lesbar[0]
        t = self.t
        menue = self._menue()
        menue.add_command(label=t("ps4ota.deinst_game", title_id=e.title_id), command=lambda: self._ota_deinstallieren("game", e.title_id))
        menue.add_command(label=t("ps4ota.deinst_patch", title_id=e.title_id), command=lambda: self._ota_deinstallieren("patch", e.title_id))
        menue.add_command(label=t("ps4ota.deinst_ac", content_id=e.content_id), command=lambda: self._ota_deinstallieren("ac", e.content_id))
        menue.add_command(label=t("ps4ota.deinst_theme", content_id=e.content_id), command=lambda: self._ota_deinstallieren("theme", e.content_id))
        try:
            menue.tk_popup(knopf.winfo_rootx(), knopf.winfo_rooty() + knopf.winfo_height())
        finally:
            menue.grab_release()

    def _ota_deinstallieren(self, art: str, kennung: str) -> None:
        ziel = self._ota_ziel()
        if ziel is None:
            return
        ip, port = ziel
        if not messagebox.askyesno(self.t("ps4ota.window_title"), self.t("ps4ota.deinst_frage", kennung=kennung, ip=ip),
                                   parent=self.win, default="no", icon="warning"):
            return
        self.ota_status_var.set(self.t("ps4ota.ota_frage_laeuft"))

        def arbeit() -> None:
            try:
                ota.RpiClient(ip, port).deinstallieren(art, kennung)
                self._z["ota_kurz"] = ("deinstalliert", kennung, True, "")
            except ota.OtaFehler as fehler:
                self._z["ota_kurz"] = ("deinstalliert", kennung, False, str(fehler.text or fehler.schluessel))

        threading.Thread(target=arbeit, daemon=True, name="ps4ota-deinstallieren").start()

    # ------------------------------------------------------------------
    # Aufgaben
    # ------------------------------------------------------------------
    def _gewaehlte_aufgabe(self) -> "int | None":
        auswahl = self.aufg_baum.selection()
        return int(auswahl[0]) if auswahl else None

    def _aufgabe_abbrechen(self) -> None:
        kennung = self._gewaehlte_aufgabe()
        if kennung is not None:
            self.warteschlange.abbrechen(kennung)

    def _aufgabe_wiederholen(self) -> None:
        kennung = self._gewaehlte_aufgabe()
        if kennung is not None:
            self.warteschlange.wiederholen(kennung)

    def _aufgabe_entfernen(self) -> None:
        kennung = self._gewaehlte_aufgabe()
        if kennung is not None:
            self.warteschlange.entfernen(kennung)

    def _aufgaben_leeren(self) -> None:
        self.warteschlange.erledigte_leeren()

    def _aufgabe_oeffnen(self) -> None:
        kennung = self._gewaehlte_aufgabe()
        aufgabe = self.warteschlange.aufgabe(kennung) if kennung is not None else None
        if aufgabe is not None and aufgabe.ergebnis and os.path.exists(aufgabe.ergebnis):
            ziel = aufgabe.ergebnis if os.path.isdir(aufgabe.ergebnis) else os.path.dirname(aufgabe.ergebnis)
            self.g._oeffnen_oder_melden(ziel, self.t("ps4ota.window_title"), parent=self.win)

    def _aufgaben_knoepfe(self) -> None:
        kennung = self._gewaehlte_aufgabe()
        aufgabe = next((a for a in self.warteschlange.schnappschuss() if a.kennung == kennung), None)
        status = aufgabe.status if aufgabe else ""
        bs.freigeben(self.aufg_knoepfe["abbrechen"], status in (au.WARTET, au.LAEUFT))
        bs.freigeben(self.aufg_knoepfe["wiederholen"], status in (au.FEHLER, au.ABGEBROCHEN))
        bs.freigeben(self.aufg_knoepfe["entfernen"], bool(aufgabe) and status != au.LAEUFT)
        bs.freigeben(self.aufg_knoepfe["oeffnen"],
                     bool(aufgabe and aufgabe.ergebnis and os.path.exists(aufgabe.ergebnis)))

    def _aufgaben_anzeigen(self) -> None:
        t = self.t
        schnappschuss = self.warteschlange.schnappschuss()
        gewaehlt = self.aufg_baum.selection()
        vorhandene = set(self.aufg_baum.get_children())
        kennungen = set()
        status_text = {au.WARTET: t("ps4ota.aufg_wartet"), au.LAEUFT: t("ps4ota.aufg_laeuft"), au.FERTIG: t("ps4ota.aufg_fertig"),
                       au.FEHLER: t("ps4ota.aufg_fehler"), au.ABGEBROCHEN: t("ps4ota.aufg_abgebrochen")}
        art_text = {"entpacken": t("ps4ota.art_entpacken"), "einzeln": t("ps4ota.art_einzeln"), "zusammen": t("ps4ota.art_zusammen"),
                    "neu_packen": t("ps4ota.art_neu_packen"), "pruefen": t("ps4ota.art_pruefen"), "bauen": t("ps4ota.art_bauen"),
                    "update": t("ps4ota.art_update"), "ota": t("ps4ota.art_ota")}
        for index, a in enumerate(schnappschuss):
            iid = str(a.kennung)
            kennungen.add(iid)
            meldung = a.fehler if a.status == au.FEHLER else a.text
            werte = (art_text.get(a.art, a.art), a.titel, status_text.get(a.status, a.status),
                     "%d %%" % a.prozent if a.status in (au.LAEUFT, au.FERTIG) else "", meldung)
            tag = (a.status,) if a.status in (au.FEHLER, au.FERTIG, au.LAEUFT) else ()
            if iid in vorhandene:
                self.aufg_baum.item(iid, values=werte, tags=tag)
                self.aufg_baum.move(iid, "", index)
            else:
                self.aufg_baum.insert("", index, iid=iid, values=werte, tags=tag)
        for iid in vorhandene - kennungen:
            self.aufg_baum.delete(iid)
        if gewaehlt:
            erhalten = [i for i in gewaehlt if i in kennungen]
            if erhalten:
                self.aufg_baum.selection_set(erhalten)
        laufende = [a for a in schnappschuss if a.status in (au.WARTET, au.LAEUFT)]
        self.aufg_gesamt.setzen((sum(a.prozent for a in schnappschuss if a.status in (au.WARTET, au.LAEUFT))
                                 / len(laufende)) if laufende else 0)
        self._aufgaben_knoepfe()
        # Enden ins Protokoll (und einmal ins Hauptprotokoll).
        for a in schnappschuss:
            if a.status in au.ENDZUSTAENDE and a.kennung not in self._gemeldet:
                self._gemeldet.add(a.kennung)
                self._aufgabe_beendet(a)

    def _aufgabe_beendet(self, a: au.Aufgabe) -> None:
        t = self.t
        if a.status == au.FERTIG:
            self._log(t("ps4ota.log_aufgabe_fertig", titel=a.titel, ergebnis=a.ergebnis))
            try:
                self.g._append_to_log(t("ps4ota.main_log_fertig", titel=a.titel, ergebnis=a.ergebnis) + "\n")
            except Exception:  # noqa: BLE001
                pass
        elif a.status == au.FEHLER:
            self._log(t("ps4ota.log_aufgabe_fehler", titel=a.titel, fehler=a.fehler))
        else:
            self._log(t("ps4ota.log_aufgabe_abgebrochen", titel=a.titel))

    # ------------------------------------------------------------------
    # Takt
    # ------------------------------------------------------------------
    def _takt(self) -> None:
        if self._schliesst:
            return
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        z = self._z
        try:
            if z.get("scan_laeuft"):
                text = z.get("scan_text")
                suche = z.get("scan_suche")
                if text:
                    self.status_var.set(self.t("ps4ota.scan_fortschritt", aktuell=text[0], gesamt=text[1], datei=text[2]))
                elif suche:
                    # Noch beim Suchen nach den Paketen (ein ganzer Datentraeger kann Minuten dauern).
                    self.status_var.set(self.t("ps4ota.scan_suche", anzahl=suche[0],
                                               ordner=os.path.basename(suche[1].rstrip("\\/")) or suche[1]))
            elif z.get("scan_fertig"):
                self._scan_fertig()
            if z.get("bilder"):
                pfad, daten = z.pop("bilder")
                self._bilder_zeigen(pfad, daten)
            if z.get("dateien"):
                pfad, eintraege, fehler = z.pop("dateien")
                self._dateien_zeigen(pfad, eintraege, fehler)
            if z.get("update_ergebnis"):
                self._update_ergebnis(*z.pop("update_ergebnis"))
            if z.get("online_text") and z.get("online_laeuft"):
                nr, gesamt, title_id = z["online_text"]
                self.status_var.set(self.t("ps4ota.update_alle_fortschritt", aktuell=nr, gesamt=gesamt, title_id=title_id))
            if z.get("online_ergebnis") is not None and not z.get("online_laeuft"):
                ergebnisse, fehler = z.pop("online_ergebnis")
                self._online.update(ergebnisse)
                bs.freigeben(self.update_alle, True)
                self._log(self.t("ps4ota.log_update_alle_fertig", anzahl=len(ergebnisse),
                                 neuer=sum(1 for i, v in ergebnisse.items() if v and upd.ist_neuer(v, self._lokal_neueste(i)))))
                if fehler:
                    self._log(self.t("ps4ota.log_update_alle_netz", fehler=fehler))
                self._tabelle_neu()
            if z.get("ota_erkannt") is not None:
                self._ota_erkannt_zeigen(z.pop("ota_erkannt"))
            if z.get("ota_kurz"):
                art, kennung, ok, fehler = z.pop("ota_kurz")
                self._ota_kurz_zeigen(art, kennung, ok, fehler)
            if z.get("aufgaben_geaendert") or self.warteschlange.beschaeftigt:
                z["aufgaben_geaendert"] = False
                self._aufgaben_anzeigen()
            for ordner in z.pop("oeffnen", []):
                if os.path.isdir(ordner):
                    self.g._oeffnen_oder_melden(ordner, self.t("ps4ota.window_title"), parent=self.win)
            self._protokoll_leeren_puffer()
        except tk.TclError:
            return
        except Exception:  # noqa: BLE001
            logger.exception("Takt von PS4 PKG -> OTA gescheitert")
        try:
            self._takt_id = self.win.after(150, self._takt)
        except tk.TclError:
            pass

    def _ota_kurz_zeigen(self, art: str, kennung: str, ok: bool, fehler: str) -> None:
        t = self.t
        if fehler:
            self.ota_status_var.set(t("ps4ota.ota_kurz_fehler", fehler=fehler))
            self._log(t("ps4ota.ota_kurz_fehler", fehler=fehler))
        elif art == "installiert":
            text = t("ps4ota.ota_ist_da", kennung=kennung) if ok else t("ps4ota.ota_ist_nicht_da", kennung=kennung)
            self.ota_status_var.set(text)
            self._log(text)
        else:
            text = t("ps4ota.deinst_fertig", kennung=kennung)
            self.ota_status_var.set(text)
            self._log(text)

    def _protokoll_leeren_puffer(self) -> None:
        puffer = self._z["log"]
        if self._log_cursor >= len(puffer):
            return
        while self._log_cursor < len(puffer):
            self.protokoll.insert("end", puffer[self._log_cursor] + "\n")
            self._log_cursor += 1
        self.protokoll.see("end")

    # ------------------------------------------------------------------
    # Schliessen
    # ------------------------------------------------------------------
    def _schliessen(self) -> None:
        if self.warteschlange.offen:
            if not messagebox.askyesno(self.t("ps4ota.window_title"), self.t("ps4ota.schliessen_frage"),
                                       parent=self.win, default="no"):
                return
            self.warteschlange.alle_abbrechen()
        self._schliesst = True
        self._z["scan_abbruch"] = True
        self._z["online_abbruch"] = True
        try:
            if getattr(self.g, FENSTER_ATTRIBUT, None) is self:
                setattr(self.g, FENSTER_ATTRIBUT, None)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _bei_zerstoerung(self, ereignis) -> None:
        """Das Fenster wird ohne ``_schliessen`` zerstoert (``destroy`` von aussen).

        Dann haengt das Programm sonst weiter an dem toten Fensterobjekt (``FENSTER_ATTRIBUT``), samt Bildern und
        Zeichnern, bis das naechste Fenster es ersetzt - und die Laeufe im Hintergrund erfahren nicht, dass es
        niemanden mehr gibt, dem sie berichten.
        """
        if ereignis.widget is not self.win:
            return
        self._schliesst = True
        z = getattr(self, "_z", None)
        if isinstance(z, dict):
            z["scan_abbruch"] = True
            z["online_abbruch"] = True
        try:
            if getattr(self.g, FENSTER_ATTRIBUT, None) is self:
                setattr(self.g, FENSTER_ATTRIBUT, None)
        except Exception:  # noqa: BLE001
            pass


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int], *, autoladen: bool = True) -> Ps4OtaFenster:
    """Oeffnet das Fenster - oder holt das offene nach vorn (es gibt nur eins)."""
    vorhanden = getattr(gui, FENSTER_ATTRIBUT, None)
    if vorhanden is not None:
        try:
            if vorhanden.win.winfo_exists():
                vorhanden.win.deiconify()
                vorhanden.win.lift()
                vorhanden.win.focus_force()
                return vorhanden
        except tk.TclError:
            pass
    fenster = Ps4OtaFenster(gui, schrift, mono, pt, autoladen=autoladen)
    setattr(gui, FENSTER_ATTRIBUT, fenster)
    return fenster
