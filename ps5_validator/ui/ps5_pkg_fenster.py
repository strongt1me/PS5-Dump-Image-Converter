# -*- coding: utf-8 -*-
"""Das Fenster „PS5 PKG Dump & Image Converter“ (seit v1.9.71), unter WEITERE TOOLS.

Eine Oberflaeche in Karten nach dem Vorbild von PS5-PKG-IMAGE-CONVERTER 1.5.3 (Nutzerwunsch 08.10.2026):

* **Umwandeln** - Quelle (ein PS5-Paket ``.pkg`` oder ein Spielordner, per Ablegen oder Klick), Aktion (Erstellen /
  Umwandeln, Extrahieren, Pruefen), Zielformat als Kacheln, Auftrag mit Fortschritt, rechts das Ergebnis.
* **Bibliothek** - die Pakete und Spielordner mit Suche, Cover und technischer Uebersicht.

Die Arbeit am Paket macht ``ffpfsc-pkg-tool`` (:mod:`ps5_validator.utils.ps5_pkg_werkzeug`): lesen, pruefen,
entpacken, bauen. **Umwandeln** eines Pakets entpackt das Spiel in einen Arbeitsordner und uebergibt ihn an
**Aufgabe 1** des Hauptprogramms (``pack_folder`` mit dem gewaehlten Zielformat) - so gelten dort dieselben
Pruefungen, derselbe Fortschritt und die Haken fuer AMPR EMU und BACKPORT; ein Spielordner geht ohne Entpacken
direkt dorthin. **Extrahieren** schreibt den Dump-Ordner direkt ins Ziel. Die Kachel **Paket** baut aus einem
Spielordner ein Debug-Paket (FPKG) und prueft es danach.

**Faeden:** Arbeitsfaeden fassen nie ein Widget oder eine Tk-Variable an; sie schreiben unter ``self._sperre`` in
``self._z``, ein Takt im Fensterfaden (:meth:`_takt`) liest das (siehe ``project_tk_faden_variablen``).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import ps5_pkg_werkzeug as wz

logger = logging.getLogger("PS5Converter.ui.ps5_pkg_fenster")

FENSTER_ATTRIBUT = "_ps5_pkg_fenster"
TAKT_MS = 250

EINST_ZIEL = "ps5pkg_ziel"
EINST_FORMAT = "ps5pkg_format"
EINST_BIBLIOTHEK = "ps5pkg_bibliothek"
EINST_AKTION = "ps5pkg_aktion"

AKTION_UMWANDELN = "umwandeln"
AKTION_EXTRAHIEREN = "extrahieren"
AKTION_PRUEFEN = "pruefen"
AKTIONEN = (AKTION_UMWANDELN, AKTION_EXTRAHIEREN, AKTION_PRUEFEN)

#: Zielformate: (Schluessel des Hauptprogramms, Kachelname, Endung). ``pkg`` ist kein Format von Aufgabe 1, sondern der
#: Bau eines Debug-Pakets aus einem Spielordner (nur dort waehlbar).
FORMATE = (("ffpkg", "FFPKG", ".ffpkg"), ("ffpfsc", "FFPFSC", ".ffpfsc"), ("ffpfs", "FFPFS", ".ffpfs"),
           ("exfat", "exFAT", ".exfat"), ("pkg", "Paket", ".pkg"))
FORMAT_PAKET = "pkg"

#: Ab wie viel freiem Platz (Vielfaches der Quellgroesse) das Fenster beim Bauen nachfragt bzw. abbricht. Gemessen am
#: 09.10.2026: Ein 1,2-GB-Spiel wurde in ein 541-MB-Paket; auf einem Laufwerk ohne feste Verknuepfungen (exFAT) legt
#: das Werkzeug erst eine Kopie des Spiels an.
BAU_PLATZ_WARNUNG = 2.0
BAU_PLATZ_MINDEST = 1.05
#: Ein entpacktes Spiel ist groesser als sein Paket (gemessen: 939 MB -> 1,55 GB).
ENTPACKT_FAKTOR = 1.7

_UNZULAESSIG = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _haupt(gui):
    return sys.modules.get(type(gui).__module__)


def sauberer_name(text: str) -> str:
    """Ein Dateiname fuer Windows, Linux und macOS."""
    name = _UNZULAESSIG.sub(" ", text or "").strip(" .")
    return re.sub(r"\s+", " ", name)


def anzeigename(info: "wz.PaketInfo") -> str:
    """``Titel [PPSA00000]`` - so heissen Entpackordner und Abbilder."""
    name = os.path.basename(os.path.normpath(info.pfad))
    titel = sauberer_name(info.titel) or sauberer_name(name if info.ist_ordner else os.path.splitext(name)[0])
    return "%s [%s]" % (titel, info.title_id) if info.title_id and info.title_id not in titel else titel


_GROESSE = re.compile(r"^(?:gr(?:ö|oe)(?:ß|ss)e|size):(<=|>=|<|>)?(\d+(?:[.,]\d+)?)\s*(kb|mb|gb|tb)?$", re.IGNORECASE)
_EINHEIT = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4, "": 1}


def _wort_passt(info: "wz.PaketInfo", wort: str) -> bool:
    klein = wort.lower()
    for vorsatz in ("titel:", "title:"):
        if klein.startswith(vorsatz):
            return klein[len(vorsatz):] in (info.titel or "").lower()
    if klein.startswith("id:"):
        rest = klein[3:]
        return rest in info.title_id.lower() or rest in info.content_id.lower()
    treffer = _GROESSE.match(wort)
    if treffer:
        vergleich = treffer.group(1) or ">="
        grenze = float(treffer.group(2).replace(",", ".")) * _EINHEIT[(treffer.group(3) or "").lower()]
        return {"<": info.groesse < grenze, "<=": info.groesse <= grenze, ">": info.groesse > grenze,
                ">=": info.groesse >= grenze}[vergleich]
    heu = " ".join([info.titel, info.title_id, info.content_id, os.path.basename(info.pfad)]).lower()
    return klein in heu


def suche_passt(info: "wz.PaketInfo", suche: str) -> bool:
    """Passt das Paket zur Suche? Mehrere Woerter gelten zusammen; ``-wort`` schliesst aus; ``titel:``, ``id:`` und
    ``groesse:>50GB`` (auch ``<``, ``>=``, ``<=``) schraenken ein."""
    for wort in suche.split():
        ausschluss = wort.startswith("-") and len(wort) > 1
        passt = _wort_passt(info, wort[1:] if ausschluss else wort)
        if passt == ausschluss:
            return False
    return True


def firmware_text(wert) -> str:
    """``0x0900000000000000`` -> ``9.00``; sonst der Wert, wie er ist."""
    try:
        zahl = int(str(wert), 16) if str(wert).lower().startswith("0x") else int(wert)
    except (TypeError, ValueError):
        return str(wert or "")
    haupt, neben = (zahl >> 56) & 0xFF, (zahl >> 48) & 0xFF
    return "%x.%02x" % (haupt, neben) if zahl else ""


KATEGORIEN = {0: "Spiel", 1: "Anwendung", 2: "Zusatzinhalt"}


def uebersicht(info: "wz.PaketInfo", t: Callable[..., str], fmt: Callable[[int], str]) -> list[tuple[str, str]]:
    """Die Zeilen der technischen Uebersicht - (Eigenschaft, Wert)."""
    p = info.param if isinstance(info.param, dict) else {}
    lokal = p.get("localizedParameters") if isinstance(p.get("localizedParameters"), dict) else {}
    zeilen = [
        ("title", info.titel or "-"),
        ("source", t("ps5pkg.src_folder") if info.ist_ordner else (t("ps5pkg.src_debug") if info.debug else (info.typ or "-"))),
        ("size", fmt(info.groesse)),
        ("title_id", info.title_id or "-"),
        ("content_id", info.content_id or "-"),
        ("concept", str(p.get("conceptId", "") or "-")),
        ("version", str(p.get("contentVersion", "") or "-")),
        ("master", str(p.get("masterVersion", "") or "-")),
        ("firmware", firmware_text(p.get("requiredSystemSoftwareVersion", "")) or "-"),
        ("sdk", firmware_text(p.get("sdkVersion", "")) or "-"),
        ("category", KATEGORIEN.get(p.get("applicationCategoryType"), str(p.get("applicationCategoryType", "-")))),
        ("drm", str(p.get("applicationDrmType", "") or info.drm_typ)),
        ("badge", str(p.get("contentBadgeType", "-"))),
        ("language", str(lokal.get("defaultLanguage", "") or "-")),
    ]
    return [(t("ps5pkg.prop_" + k), v) for k, v in zeilen]


class Ps5PkgFenster:
    """Das Fenster. Eine Instanz je geoeffnetem Fenster."""

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int], vorgabe: str = "") -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.pakete: list[wz.PaketInfo] = []
        self.aktuell: "wz.PaketInfo | None" = None
        self.format_schluessel = "ffpfsc"
        self._sperre = threading.Lock()
        self._z: dict = {"zeilen": [], "prozent": None, "schritt_text": None, "schritt": None, "fertig": None,
                         "gelesen": [], "lesen_laeuft": 0}
        self._abbruch = False
        self._schliesst = False
        self._takt_id = None
        self._job: "dict | None" = None            # laufender Auftrag
        self._uebergabe: "dict | None" = None      # Hand-off an Aufgabe 1
        self._cover = None
        self._cover_ordner: list[str] = []
        self._staging: list[str] = []
        self._kacheln: dict[str, tuple] = {}
        self._bau: dict = {}                       # Arbeitsordner und Vorher-Stand des laufenden Baus
        self._werkzeug_pfad = ""
        self._bauen(vorgabe)
        self._takt()

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
        except Exception as exc:  # noqa: BLE001
            logger.debug("Einstellung %s nicht gespeichert: %s", schluessel, exc)

    def _wurzeln(self) -> list[str]:
        wurzeln = [os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            wurzeln.insert(0, str(meipass))
        return wurzeln

    def _werkzeug(self) -> str:
        if not self._werkzeug_pfad or not os.path.isfile(self._werkzeug_pfad):
            self._werkzeug_pfad = wz.werkzeug_suchen(self._wurzeln())
        return self._werkzeug_pfad

    def _popen_extra(self) -> dict:
        haupt = _haupt(self.g)
        if sys.platform == "win32" and haupt is not None:
            return {"creationflags": getattr(haupt, "_NO_WIN_FLAGS", 0),
                    "startupinfo": haupt._silent_startupinfo()}
        return {}

    def _fmt(self, n: int) -> str:
        try:
            return self.g._fmt_bytes(int(n))
        except Exception:  # noqa: BLE001
            return "%d B" % n

    def _protokoll(self, text: str) -> None:
        try:
            self.protokoll.configure(state="normal")
            self.protokoll.insert("end", text + "\n")
            self.protokoll.see("end")
            self.protokoll.configure(state="disabled")
        except tk.TclError:
            pass

    def _melden(self, text: str) -> None:
        """Aus jedem Faden: eine Zeile fuers Protokoll."""
        with self._sperre:
            self._z["zeilen"].append(text)

    def _status(self, text: str) -> None:
        try:
            self.status_var.set(text)
        except tk.TclError:
            pass

    def _arbeitsordner(self) -> str:
        try:
            basis = self.g._get_runtime_temp_dir()
        except Exception:  # noqa: BLE001
            basis = ""
        return basis if basis and os.path.isdir(basis) else tempfile.gettempdir()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _karte(self, eltern, titel_schluessel: str, polster=(16, 12)):
        """Eine runde Karte mit Ueberschrift; die Kinder entstehen in der Karte selbst.

        ``pw.Karte`` statt ``_runde_seitenkarte``: Das Hauptprogramm hielte jede Karte seiner Seiten in einer Liste fest,
        ein geschlossenes Fenster liesse sie samt Bildern stehen (``test_fenster_leck``).
        """
        karte = self.g._pw.Karte(eltern, bg=self.c["bg_card"], padx=polster[0], pady=polster[1])
        tk.Label(karte, text=self.t(titel_schluessel).upper(), font=(self.F, self.pt(10), "bold"),
                 bg=self.c["bg_card"], fg=self.c["fg_primary"], anchor="w").pack(fill="x", pady=(0, 8))
        return karte

    def _pille(self, eltern, schluessel: str, befehl, akzent: bool = False, klein: bool = False):
        """Ein Knopf des Fensters (``pw.Button``: nichts davon bleibt im Hauptprogramm stehen)."""
        optionen = {"style": "Accent.TButton"} if akzent else {}
        return self.g._pw.Button(eltern, text=self.t(schluessel), command=befehl, **optionen)

    def _bauen(self, vorgabe: str) -> None:
        g, t, c = self.g, self.t, self.c
        F, pt = self.F, self.pt
        titel = t("ps5pkg.window_title")
        self.win = g._build_modern_toplevel(titel, 1240, 840, min_width=1060, min_height=700)
        self.win.configure(bg=c["bg_main"])
        self.status_var = tk.StringVar(value=t("ps5pkg.status_idle"))
        self.ziel_var = tk.StringVar(value=str(self._einstellung(EINST_ZIEL, "") or ""))
        if not self.ziel_var.get() and hasattr(g, "dest_path"):
            self.ziel_var.set(g.dest_path.get().strip())
        self.aktion_var = tk.StringVar(value=str(self._einstellung(EINST_AKTION, AKTION_UMWANDELN)))
        if self.aktion_var.get() not in AKTIONEN:
            self.aktion_var.set(AKTION_UMWANDELN)
        gespeichert = str(self._einstellung(EINST_FORMAT, "ffpfsc"))
        self.format_schluessel = gespeichert if gespeichert in [f[0] for f in FORMATE] else "ffpfsc"
        self.ueberschreiben_var = tk.BooleanVar(value=False)
        self.schritt_var = tk.StringVar(value="0 %")
        self.auftrag_var = tk.StringVar(value=t("ps5pkg.job_ready"))

        # Statuszeile und Knopfleiste unten (zuerst packen - sonst quetscht sie die Mindesthoehe weg)
        status = tk.Frame(self.win, bg=c["bg_main"], padx=14, pady=5)
        status.pack(side="bottom", fill="x")
        tk.Label(status, textvariable=self.status_var, font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                 anchor="w").pack(side="left")
        self.zaehler_var = tk.StringVar(value="")
        tk.Label(status, textvariable=self.zaehler_var, font=(F, pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"]).pack(side="right")
        leiste = tk.Frame(self.win, bg=c["bg_main"], padx=14, pady=8)
        leiste.pack(side="bottom", fill="x")
        self.start_knopf = self._pille(leiste, "ps5pkg.start_button", self._starten, akzent=True)
        self.start_knopf.pack(side="left")
        self.abbrechen_knopf = self._pille(leiste, "action.cancel", self._abbrechen)
        self.abbrechen_knopf.pack(side="left", padx=(10, 0))
        self.abbrechen_knopf.configure(state="disabled")

        rumpf = tk.Frame(self.win, bg=c["bg_main"])
        rumpf.pack(fill="both", expand=True)
        rumpf.columnconfigure(1, weight=1)
        rumpf.rowconfigure(0, weight=1)
        self._navigation(rumpf)
        flaeche = tk.Frame(rumpf, bg=c["bg_main"])
        flaeche.grid(row=0, column=1, sticky="nsew", padx=(0, 14))
        flaeche.columnconfigure(0, weight=1)
        flaeche.rowconfigure(0, weight=1)
        self.seiten = {"umwandeln": tk.Frame(flaeche, bg=c["bg_main"]), "bibliothek": tk.Frame(flaeche, bg=c["bg_main"])}
        for seite in self.seiten.values():
            seite.grid(row=0, column=0, sticky="nsew")
        self._seite_umwandeln(self.seiten["umwandeln"])
        self._seite_bibliothek(self.seiten["bibliothek"])
        self._seite_zeigen("umwandeln")

        self.win.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.win.bind("<Destroy>", self._bei_zerstoerung, add="+")
        self._aktion_anwenden()
        self._bibliothek_laden()
        if vorgabe:
            self.win.after(200, lambda: self._pakete_hinzufuegen([p for p in vorgabe.split(os.pathsep) if p.strip()]))

    def _navigation(self, eltern) -> None:
        c, F, pt = self.c, self.F, self.pt
        leiste = tk.Frame(eltern, bg=c["bg_main"], width=104)
        leiste.grid(row=0, column=0, sticky="ns", padx=(10, 12), pady=10)
        leiste.grid_propagate(False)
        self._nav: dict[str, tuple[tk.Frame, tk.Label, tk.Label]] = {}
        for schluessel, zeichen, text in (("umwandeln", "⇄", "ps5pkg.nav_convert"), ("bibliothek", "▥", "ps5pkg.nav_library")):
            rahmen = tk.Frame(leiste, bg=c["bg_main"], cursor="hand2", pady=8)
            rahmen.pack(fill="x", pady=(0, 6))
            symbol = tk.Label(rahmen, text=zeichen, font=(F, pt(18)), bg=c["bg_main"], fg=c["fg_secondary"])
            symbol.pack()
            name = tk.Label(rahmen, text=self.t(text), font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"])
            name.pack()
            for w in (rahmen, symbol, name):
                w.bind("<Button-1>", lambda _e, s=schluessel: self._seite_zeigen(s))
            self._nav[schluessel] = (rahmen, symbol, name)

    def _seite_zeigen(self, schluessel: str) -> None:
        c = self.c
        self.seiten[schluessel].tkraise()
        for name, (rahmen, symbol, text) in self._nav.items():
            aktiv = name == schluessel
            farbe = c["fg_accent"] if aktiv else c["fg_secondary"]
            rahmen.configure(bg=c["bg_card"] if aktiv else c["bg_main"])
            symbol.configure(bg=c["bg_card"] if aktiv else c["bg_main"], fg=farbe)
            text.configure(bg=c["bg_card"] if aktiv else c["bg_main"], fg=c["fg_primary"] if aktiv else c["fg_secondary"])
        self.aktuelle_seite = schluessel
        if hasattr(self, "start_knopf"):
            self._knoepfe_pruefen()

    # ---------------- Seite Umwandeln ----------------
    def _seite_umwandeln(self, seite) -> None:
        g, t, c = self.g, self.t, self.c
        F, pt = self.F, self.pt
        pw = g._pw
        seite.columnconfigure(0, weight=1)
        seite.rowconfigure(1, weight=1)
        kopf = tk.Frame(seite, bg=c["bg_main"])
        kopf.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        tk.Label(kopf, text=t("ps5pkg.page_title"), font=(F, pt(20), "bold"), bg=c["bg_main"], fg=c["fg_primary"],
                 anchor="w").pack(fill="x")
        tk.Label(kopf, text=t("ps5pkg.page_subtitle"), font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_secondary"],
                 anchor="w").pack(fill="x")

        links = tk.Frame(seite, bg=c["bg_main"])
        links.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        links.columnconfigure(0, weight=1)
        links.rowconfigure(2, weight=1)
        rechts = tk.Frame(seite, bg=c["bg_main"], width=380)
        rechts.grid(row=1, column=1, sticky="ns")
        rechts.grid_propagate(False)

        # QUELLE
        quelle = self._karte(links, "ps5pkg.card_source")
        quelle.grid(row=0, column=0, sticky="ew")
        oben = tk.Frame(quelle, bg=c["bg_card"])
        oben.pack(fill="x")
        oben.columnconfigure(0, weight=1)
        self.ablage = tk.Canvas(oben, height=74, bg=c["bg_card"], highlightthickness=0, cursor="hand2")
        self.ablage.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.ablage.bind("<Configure>", self._ablage_malen)
        self.ablage.bind("<Button-1>", lambda _e: self._datei_waehlen())
        rechts_k = tk.Frame(oben, bg=c["bg_card"])
        rechts_k.grid(row=0, column=1, sticky="ns")
        self._pille(rechts_k, "ps5pkg.choose_file", self._datei_waehlen, klein=True).pack(fill="x", pady=(0, 6))
        self._pille(rechts_k, "ps5pkg.choose_folder", self._ordner_waehlen, klein=True).pack(fill="x")
        haupt = _haupt(g)
        dnd = getattr(haupt, "DND_FILES", None)
        if dnd:
            try:
                self.ablage.drop_target_register(dnd)
                self.ablage.dnd_bind("<<Drop>>", self._abgelegt)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ablegen nicht verfuegbar: %s", exc)

        self.paket_titel = tk.Label(quelle, text=t("ps5pkg.no_source"), font=(F, pt(12), "bold"),
                                    bg=c["bg_card"], fg=c["fg_primary"], anchor="w")
        self.paket_titel.pack(fill="x", pady=(12, 0))
        zeile = tk.Frame(quelle, bg=c["bg_card"])
        zeile.pack(fill="x")
        self.paket_pfad = tk.Label(zeile, text="", font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"], anchor="w")
        self.paket_pfad.pack(side="left", fill="x", expand=True)
        self.paket_typ = tk.Label(zeile, text="", font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_accent"], padx=10)
        self.paket_typ.pack(side="right")
        aktion = tk.Frame(quelle, bg=c["bg_card"])
        aktion.pack(fill="x", pady=(10, 0))
        tk.Label(aktion, text=t("ps5pkg.action_label"), font=(F, pt(10)), bg=c["bg_card"], fg=c["fg_secondary"]).pack(
            side="left", padx=(0, 12))
        self._aktion_knoepfe = {}
        for wert, schluessel in ((AKTION_UMWANDELN, "ps5pkg.action_convert"), (AKTION_EXTRAHIEREN, "ps5pkg.action_extract"),
                                 (AKTION_PRUEFEN, "ps5pkg.action_check")):
            knopf = pw.Radiobutton(aktion, text=t(schluessel), value=wert, variable=self.aktion_var, font=(F, pt(10)),
                                   command=self._aktion_geaendert, bg=c["bg_card"], fg=c["fg_primary"],
                                   selectcolor=c["bg_card"], activebackground=c["bg_card"],
                                   activeforeground=c["fg_primary"], highlightthickness=0, bd=0)
            knopf.pack(side="left", padx=(0, 14))
            self._aktion_knoepfe[wert] = knopf
        ziel = tk.Frame(quelle, bg=c["bg_card"])
        ziel.pack(fill="x", pady=(10, 0))
        ziel.columnconfigure(1, weight=1)
        tk.Label(ziel, text=t("ps5pkg.target_folder"), font=(F, pt(10)), bg=c["bg_card"], fg=c["fg_secondary"]).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.ziel_feld = pw.Entry(ziel, textvariable=self.ziel_var, font=(F, pt(10)), bg=c["bg_main"],
                                  fg=c["fg_primary"], insertbackground=c["fg_primary"], relief="flat")
        self.ziel_feld.grid(row=0, column=1, sticky="ew", ipady=3)
        self._pille(ziel, "ps5pkg.choose_target", self._ziel_waehlen, klein=True).grid(row=0, column=2, padx=(8, 0))
        self.ueberschreiben = pw.Checkbutton(quelle, text=t("ps5pkg.overwrite"), variable=self.ueberschreiben_var,
                                             font=(F, pt(10)))
        self.ueberschreiben.pack(anchor="w", pady=(6, 0))

        # ZIELFORMAT
        formate = self._karte(links, "ps5pkg.card_format")
        formate.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        reihe = tk.Frame(formate, bg=c["bg_card"])
        reihe.pack(fill="x")
        for i, (schluessel, name, endung) in enumerate(FORMATE):
            reihe.columnconfigure(i, weight=1, uniform="kachel")
            self._kachel(reihe, i, schluessel, name, endung)
        self._kacheln_faerben()

        # AUFTRAG
        auftrag = self._karte(links, "ps5pkg.card_job")
        auftrag.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        tk.Label(auftrag, textvariable=self.auftrag_var, font=(F, pt(11), "bold"), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w", wraplength=700, justify="left").pack(fill="x")
        balken = tk.Frame(auftrag, bg=c["bg_card"])
        balken.pack(fill="x", pady=(8, 0))
        balken.columnconfigure(1, weight=1)
        tk.Label(balken, text=t("ps5pkg.step_progress"), font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"]).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.balken = pw.Progressbar(balken, mode="determinate", maximum=100.0)
        self.balken.grid(row=0, column=1, sticky="ew", pady=2)
        tk.Label(balken, textvariable=self.schritt_var, width=6, anchor="e", font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_primary"]).grid(row=0, column=2, padx=(8, 0))
        tk.Label(balken, text=t("ps5pkg.job_steps"), font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"]).grid(
            row=1, column=0, sticky="w", padx=(0, 12))
        self.balken_gesamt = pw.Progressbar(balken, mode="determinate", maximum=100.0)
        self.balken_gesamt.grid(row=1, column=1, sticky="ew", pady=2)
        # Die Textknoepfe zuerst unten packen - sonst quetscht sie das Protokoll bei kleiner Fensterhoehe weg.
        textknoepfe = tk.Frame(auftrag, bg=c["bg_card"])
        textknoepfe.pack(side="bottom", fill="x")
        self.ausgabe_knopf = self._pille(textknoepfe, "ps5pkg.open_output", self._ausgabe_oeffnen, klein=True)
        self.ausgabe_knopf.pack(side="left")
        self._pille(textknoepfe, "ps5pkg.clear_log", self._verlauf_leeren, klein=True).pack(side="left", padx=(8, 0))
        self.protokoll = pw.Text(auftrag, height=6, font=(self.M, pt(9)), bg=c["console_bg"], fg=c["console_fg"],
                                 relief="flat", wrap="word", state="disabled")
        self.protokoll.pack(fill="both", expand=True, pady=(8, 8))

        # ERGEBNIS
        ergebnis = self._karte(rechts, "ps5pkg.card_result")
        ergebnis.pack(fill="x")
        self.ergebnis_var = {}
        for schluessel in ("output", "title_id", "content", "size", "free"):
            zeile = tk.Frame(ergebnis, bg=c["bg_card"])
            zeile.pack(fill="x", pady=2)
            tk.Label(zeile, text=t("ps5pkg.res_" + schluessel), font=(F, pt(10)), bg=c["bg_card"],
                     fg=c["fg_secondary"]).pack(side="left")
            var = tk.StringVar(value="")
            self.ergebnis_var[schluessel] = var
            tk.Label(zeile, textvariable=var, font=(F, pt(10)), bg=c["bg_card"], fg=c["fg_primary"], anchor="e",
                     wraplength=210, justify="right").pack(side="right", fill="x", expand=True)

    def _kachel(self, eltern, spalte: int, schluessel: str, name: str, endung: str) -> None:
        g, c, F, pt = self.g, self.c, self.F, self.pt
        karte = raster.RundeKarte(eltern, g._bibliothek_zeichner(), fuellung="bg_main", rand="border", grund="bg_card",
                                  radius=g._KARTEN_ECKE, polster=(6, 4))
        karte.grid(row=0, column=spalte, sticky="ew", padx=(0 if spalte == 0 else 8, 0))
        l1 = tk.Label(karte.innen, text=name, font=(F, pt(11), "bold"), bg=c["bg_main"], fg=c["fg_primary"], cursor="hand2")
        l1.pack(pady=(8, 0))
        l2 = tk.Label(karte.innen, text=endung, font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"], cursor="hand2")
        l2.pack(pady=(0, 8))
        for w in (karte, karte.innen, l1, l2):
            w.bind("<Button-1>", lambda _e, s=schluessel: self._format_waehlen(s))
        self._kacheln[schluessel] = (karte, l1, l2)

    def _aktion_moeglich(self, aktion: str) -> bool:
        """Ein Spielordner kennt nur Erstellen / Umwandeln - entpacken und pruefen gibt es nur fuer Pakete."""
        info = self.aktuell
        return info is None or not info.ist_ordner or aktion == AKTION_UMWANDELN

    def _format_moeglich(self, schluessel: str) -> bool:
        """Die Kachel Paket (Bau eines Debug-Pakets) gibt es nur fuer einen Spielordner."""
        info = self.aktuell
        return schluessel != FORMAT_PAKET or info is None or info.ist_ordner

    def _kacheln_faerben(self) -> None:
        c = self.c
        gesperrt = self.aktion_var.get() != AKTION_UMWANDELN
        for schluessel, (karte, l1, l2) in self._kacheln.items():
            frei = self._format_moeglich(schluessel)
            aktiv = schluessel == self.format_schluessel and not gesperrt and frei
            fuellung = "accent_btn" if aktiv else "bg_main"
            karte._rollen = (fuellung, "fg_accent" if aktiv else "border", "bg_card")
            karte.neu_faerben()
            matt = gesperrt or not frei
            l1.configure(bg=c[fuellung], fg=("white" if aktiv else (c["fg_secondary"] if matt else c["fg_primary"])),
                         cursor="hand2" if frei else "arrow")
            l2.configure(bg=c[fuellung], fg=("white" if aktiv else c["fg_secondary"]), cursor="hand2" if frei else "arrow")

    def _format_waehlen(self, schluessel: str) -> None:
        if not self._format_moeglich(schluessel):
            self._status(self.t("ps5pkg.format_only_folder"))
            return
        if self.aktion_var.get() != AKTION_UMWANDELN:
            self.aktion_var.set(AKTION_UMWANDELN)
            self._aktion_geaendert()
        self.format_schluessel = schluessel
        self._merken(EINST_FORMAT, schluessel)
        self._kacheln_faerben()
        self._ergebnis_fuellen()

    def _ablage_malen(self, _e=None) -> None:
        c = self.c
        a = self.ablage
        a.delete("all")
        b, h = max(a.winfo_width(), 40), max(a.winfo_height(), 40)
        a.create_rectangle(2, 2, b - 2, h - 2, outline=c["border"], dash=(4, 4), width=1)
        a.create_text(b // 2, h // 2 - 10, text=self.t("ps5pkg.drop_title"), font=(self.F, self.pt(11), "bold"),
                      fill=c["fg_primary"])
        a.create_text(b // 2, h // 2 + 14, text=self.t("ps5pkg.drop_hint"), font=(self.F, self.pt(9)), fill=c["fg_secondary"])

    # ---------------- Seite Bibliothek ----------------
    def _seite_bibliothek(self, seite) -> None:
        g, t, c = self.g, self.t, self.c
        F, pt = self.F, self.pt
        pw = g._pw
        seite.columnconfigure(0, weight=1)
        seite.rowconfigure(1, weight=1)
        kopf = tk.Frame(seite, bg=c["bg_main"])
        kopf.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        tk.Label(kopf, text=t("ps5pkg.lib_title"), font=(F, pt(20), "bold"), bg=c["bg_main"], fg=c["fg_primary"],
                 anchor="w").pack(fill="x")
        tk.Label(kopf, text=t("ps5pkg.lib_subtitle"), font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_secondary"],
                 anchor="w").pack(fill="x")
        links = self._karte(seite, "ps5pkg.card_library")
        links.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        rechts = tk.Frame(seite, bg=c["bg_main"], width=420)
        rechts.grid(row=1, column=1, sticky="ns")
        rechts.grid_propagate(False)

        zeile = tk.Frame(links, bg=c["bg_card"])
        zeile.pack(fill="x")
        zeile.columnconfigure(0, weight=1)
        self.suche_var = tk.StringVar(value="")
        self._suche_hinweis = False
        self.suche_feld = pw.Entry(zeile, textvariable=self.suche_var, font=(F, pt(10)))
        self.suche_feld.grid(row=0, column=0, sticky="ew", ipady=4, padx=(0, 8))
        self.suche_feld.bind("<FocusIn>", lambda _e: self._suche_hinweis_setzen(False), add="+")
        self.suche_feld.bind("<FocusOut>", lambda _e: self._suche_hinweis_setzen(True), add="+")
        self._pille(zeile, "ps5pkg.lib_refresh", self._bibliothek_aktualisieren, klein=True).grid(row=0, column=1, padx=2)
        self._pille(zeile, "ps5pkg.lib_add_file", self._datei_waehlen_mehrere, klein=True).grid(row=0, column=2, padx=2)
        self._pille(zeile, "ps5pkg.lib_add_folder", self._ordner_waehlen, klein=True).grid(row=0, column=3, padx=2)
        raster.spur_bis_zerstoert(self.win, self.suche_var, self._suche_geaendert)
        rahmen = tk.Frame(links, bg=c["bg_card"])
        rahmen.pack(fill="both", expand=True, pady=(8, 0))
        spalten = ("titel", "title_id", "quelle", "groesse", "version")
        self.liste = pw.Treeview(rahmen, columns=spalten, show="headings", selectmode="browse")
        for spalte, breite in zip(spalten, (280, 100, 100, 100, 90)):
            self.liste.heading(spalte, text=t("ps5pkg.col_" + spalte), anchor="w")
            self.liste.column(spalte, width=breite, anchor="e" if spalte == "groesse" else "w")
        rolle = pw.Scrollbar(rahmen, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=rolle.set)
        self.liste.pack(side="left", fill="both", expand=True)
        rolle.pack(side="right", fill="y")
        self.liste.bind("<<TreeviewSelect>>", self._liste_gewaehlt)
        self.liste.bind("<Double-1>", lambda _e: self._zu_umwandeln())

        cover = self._karte(rechts, "ps5pkg.card_cover")
        cover.pack(fill="x")
        self.cover_label = tk.Label(cover, bg=c["bg_card"], fg=c["fg_secondary"], text=t("ps5pkg.no_cover"))
        self.cover_label.pack(pady=(0, 8), ipady=70, fill="x")
        self.cover_knopf = self._pille(cover, "ps5pkg.lib_convert", self._zu_umwandeln, akzent=True)
        self.cover_knopf.pack()
        tech = self._karte(rechts, "ps5pkg.card_tech")
        tech.pack(fill="both", expand=True, pady=(12, 0))
        self._pille(tech, "ps5pkg.copy_all", self._alles_kopieren, klein=True).pack(side="bottom", anchor="e", pady=(6, 0))
        self.tech = pw.Treeview(tech, columns=("eig", "wert"), show="headings", selectmode="browse", height=12)
        self.tech.heading("eig", text=t("ps5pkg.tech_prop"), anchor="w")
        self.tech.heading("wert", text=t("ps5pkg.tech_value"), anchor="w")
        self.tech.column("eig", width=170, anchor="w")
        self.tech.column("wert", width=210, anchor="w")
        rolle_tech = pw.Scrollbar(tech, orient="vertical", command=self.tech.yview)
        self.tech.configure(yscrollcommand=rolle_tech.set)
        self.tech.pack(fill="both", expand=True)

        self._suche_hinweis_setzen(True)       # erst jetzt: die Liste existiert

    # ------------------------------------------------------------------
    # Quelle waehlen und lesen
    # ------------------------------------------------------------------
    def _datei_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(parent=self.win, title=self.t("ps5pkg.choose_file_title"),
                                          filetypes=[(self.t("ps5pkg.filetype_pkg"), "*.pkg"),
                                                     (self.t("filetype.all_files"), "*.*")])
        if pfad:
            self._pakete_hinzufuegen([os.path.normpath(pfad)], waehlen=True)

    def _datei_waehlen_mehrere(self) -> None:
        pfade = filedialog.askopenfilenames(parent=self.win, title=self.t("ps5pkg.choose_file_title"),
                                            filetypes=[(self.t("ps5pkg.filetype_pkg"), "*.pkg"),
                                                       (self.t("filetype.all_files"), "*.*")])
        if pfade:
            self._pakete_hinzufuegen([os.path.normpath(p) for p in pfade], waehlen=True)

    def _ordner_waehlen(self) -> None:
        ordner = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.choose_folder_title"))
        if ordner:
            self._pakete_hinzufuegen([os.path.normpath(ordner)], waehlen=True)

    def _abgelegt(self, ereignis) -> None:
        try:
            pfade = [os.path.normpath(p) for p in self.win.tk.splitlist(ereignis.data)]
        except tk.TclError:
            return
        self._pakete_hinzufuegen(pfade, waehlen=True)

    def _pkg_in(self, ordner: str) -> list[str]:
        """Die ``.pkg`` in einem Ordner - eine Ebene tief (Spiele liegen oft in je einem Unterordner)."""
        gefunden: list[str] = []
        try:
            for eintrag in sorted(os.scandir(ordner), key=lambda e: e.name.lower()):
                if eintrag.is_file() and eintrag.name.lower().endswith(".pkg"):
                    gefunden.append(eintrag.path)
                elif eintrag.is_dir():
                    try:
                        for tiefer in sorted(os.scandir(eintrag.path), key=lambda e: e.name.lower()):
                            if tiefer.is_file() and tiefer.name.lower().endswith(".pkg"):
                                gefunden.append(tiefer.path)
                    except OSError:
                        continue
        except OSError:
            return []
        return gefunden

    def _quellen_in(self, ordner: str) -> list[str]:
        """Was ein Ordner hergibt: er selbst, wenn er ein Spiel ist, sonst seine ``.pkg`` und Spielordner."""
        if wz.ordner_ist_spiel(ordner):
            return [ordner]
        gefunden = self._pkg_in(ordner)
        try:
            for eintrag in sorted(os.scandir(ordner), key=lambda e: e.name.lower()):
                if eintrag.is_dir() and wz.ordner_ist_spiel(eintrag.path):
                    gefunden.append(eintrag.path)
        except OSError:
            pass
        return gefunden

    def _pakete_hinzufuegen(self, pfade: list[str], waehlen: bool = False) -> None:
        if not self._werkzeug():
            self._fehler(self.t("ps5pkg.err_no_tool"))
            return
        alle: list[str] = []
        for p in pfade:
            if os.path.isdir(p):
                alle.extend(self._quellen_in(p))
            elif os.path.isfile(p) and p.lower().endswith(".pkg"):
                alle.append(p)
        neu = [p for p in alle if p not in {i.pfad for i in self.pakete}]
        if not alle:
            self._status(self.t("ps5pkg.no_pkg_found"))
            if pfade:
                messagebox.showinfo(self.t("ps5pkg.window_title"), self.t("ps5pkg.no_pkg_found"), parent=self.win)
            return
        if waehlen:
            self._wahl_pfad = alle[0]
        self._lesen_starten(neu or [alle[0]], bekannt=not neu, waehlen=alle[0] if waehlen else "")

    def _lesen_starten(self, pfade: list[str], bekannt: bool = False, waehlen: str = "") -> None:
        """Liest die Pakete im Hintergrund (Kopfdaten, ``param.json``, Cover) und traegt sie danach ein."""
        werkzeug = self._werkzeug()
        popen_extra = self._popen_extra()
        arbeit = self._arbeitsordner()
        with self._sperre:
            self._z["lesen_laeuft"] += 1
        self._status(self.t("ps5pkg.status_reading", count=len(pfade)))

        def lauf() -> None:
            fertig: list = []
            for pfad in pfade:
                try:
                    if os.path.isdir(pfad):
                        info = wz.ordner_lesen(pfad, arbeit, melden=self._melden)
                    else:
                        info = wz.lesen(werkzeug, pfad, arbeit, popen_extra=popen_extra)
                    fertig.append(info)
                except wz.Fehler as exc:
                    self._melden(self.t("ps5pkg.log_read_failed", name=os.path.basename(pfad), grund=str(exc)))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Paket lesen")
                    self._melden(self.t("ps5pkg.log_read_failed", name=os.path.basename(pfad), grund=str(exc)))
            with self._sperre:
                self._z["gelesen"].append((fertig, waehlen))
                self._z["lesen_laeuft"] -= 1

        threading.Thread(target=lauf, daemon=True, name="ps5pkg-lesen").start()

    def _gelesen_uebernehmen(self, fertig: list, waehlen: str) -> None:
        vorhanden = {i.pfad: i for i in self.pakete}
        for info in fertig:
            if info.arbeit:
                self._cover_ordner.append(info.arbeit)       # nur der eigene Ordner mit der Kopie des Covers
            alt = vorhanden.get(info.pfad)
            if alt is not None:
                self.pakete[self.pakete.index(alt)] = info
            else:
                self.pakete.append(info)
        self._bibliothek_speichern()
        self._liste_fuellen(auswaehlen=waehlen)
        if waehlen:
            gewaehlt = next((i for i in self.pakete if i.pfad == waehlen), None)
            if gewaehlt is not None:
                self._paket_waehlen(gewaehlen_info=gewaehlt)
        elif self.aktuell is None and self.pakete:
            self._paket_waehlen(gewaehlen_info=self.pakete[0])
        self._status(self.t("ps5pkg.status_idle"))

    def _bibliothek_speichern(self) -> None:
        self._merken(EINST_BIBLIOTHEK, [i.pfad for i in self.pakete])

    def _bibliothek_laden(self) -> None:
        pfade = self._einstellung(EINST_BIBLIOTHEK, [])
        if isinstance(pfade, list):
            vorhanden = [p for p in pfade if isinstance(p, str) and os.path.exists(p)]
            if vorhanden and self._werkzeug():
                self._lesen_starten(vorhanden)

    def _bibliothek_aktualisieren(self) -> None:
        pfade = [i.pfad for i in self.pakete if os.path.exists(i.pfad)]
        self.pakete = []
        self._liste_fuellen()
        if pfade:
            self._lesen_starten(pfade)

    # ------------------------------------------------------------------
    # Anzeige
    # ------------------------------------------------------------------
    def _suche_hinweis_setzen(self, an: bool) -> None:
        """Zeigt den Hinweis in grau, solange das Feld leer ist und nicht benutzt wird."""
        if an and not self.suche_var.get() and not self._suche_hinweis:
            self._suche_hinweis = True
            self.suche_var.set(self.t("ps5pkg.search_hint"))
            tk.Entry.configure(self.suche_feld, fg=self.c["fg_secondary"])
        elif not an and self._suche_hinweis:
            self._suche_hinweis = False
            self.suche_var.set("")
            tk.Entry.configure(self.suche_feld, fg=self.c["fg_primary"])

    def _suche_geaendert(self, *_a) -> None:
        self._liste_fuellen()

    def _suche_text(self) -> str:
        return "" if self._suche_hinweis else self.suche_var.get().strip()

    def _liste_fuellen(self, auswaehlen: str = "") -> None:
        if not hasattr(self, "liste"):
            return
        suche = self._suche_text()
        self.liste.delete(*self.liste.get_children())
        gezeigt = 0
        for info in sorted(self.pakete, key=lambda i: (i.titel or i.pfad).lower()):
            if suche and not suche_passt(info, suche):
                continue
            quelle = (self.t("ps5pkg.src_folder_short") if info.ist_ordner
                      else self.t("ps5pkg.src_debug_short") if info.debug else (info.typ or "-"))
            self.liste.insert("", "end", iid=info.pfad, values=(
                info.titel or os.path.basename(info.pfad), info.title_id, quelle, self._fmt(info.groesse), info.version))
            gezeigt += 1
        self.zaehler_var.set(self.t("ps5pkg.counter", shown=gezeigt, total=len(self.pakete)))
        if auswaehlen and self.liste.exists(auswaehlen):
            self.liste.selection_set(auswaehlen)

    def _liste_gewaehlt(self, _e=None) -> None:
        auswahl = self.liste.selection()
        if not auswahl:
            return
        info = next((i for i in self.pakete if i.pfad == auswahl[0]), None)
        if info is not None:
            self._paket_waehlen(gewaehlen_info=info, aus_liste=True)

    def _paket_waehlen(self, gewaehlen_info: "wz.PaketInfo", aus_liste: bool = False) -> None:
        self.aktuell = gewaehlen_info
        info = gewaehlen_info
        self.paket_titel.configure(text="%s — %s" % (info.title_id, info.titel) if info.title_id and info.titel
                                   else (info.titel or os.path.basename(info.pfad)))
        self.paket_pfad.configure(text="%s · %s" % (info.pfad, self._fmt(info.groesse)))
        self.paket_typ.configure(text=self.t("ps5pkg.badge_folder") if info.ist_ordner
                                 else self.t("ps5pkg.badge_debug") if info.debug else (info.typ or ""))
        # Was fuer diese Quelle nicht geht, springt auf den Vorgabewert zurueck (ohne es zu speichern).
        if not self._aktion_moeglich(self.aktion_var.get()):
            self.aktion_var.set(AKTION_UMWANDELN)
        if not self._format_moeglich(self.format_schluessel):
            self.format_schluessel = "ffpfsc"
        self._aktion_anwenden()
        self._cover_zeigen(info)
        self.tech.delete(*self.tech.get_children())
        for eig, wert in uebersicht(info, self.t, self._fmt):
            self.tech.insert("", "end", values=(eig, wert))
        if not aus_liste and self.liste.exists(info.pfad):
            self.liste.selection_set(info.pfad)
        self._knoepfe_pruefen()

    def _cover_zeigen(self, info: "wz.PaketInfo") -> None:
        self._cover = None
        if info.icon and os.path.isfile(info.icon):
            try:
                from PIL import Image, ImageTk
                bild = Image.open(info.icon).convert("RGBA")
                bild.thumbnail((300, 300))
                self._cover = ImageTk.PhotoImage(bild, master=self.win)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Cover nicht lesbar: %s", exc)
        if self._cover is not None:
            self.cover_label.configure(image=self._cover, text="", compound="center")
            self.cover_label.configure(height=300)
        else:
            self.cover_label.configure(image="", text=self.t("ps5pkg.no_cover"))

    def _ziel_name(self) -> str:
        """Name des Ergebnisses: Ordner oder Datei mit Endung."""
        if self.aktuell is None:
            return ""
        name = anzeigename(self.aktuell)
        if self.aktion_var.get() == AKTION_UMWANDELN:
            if self.format_schluessel == FORMAT_PAKET:
                return "%s….pkg" % (self.aktuell.content_id or name)       # den Namen legt das Werkzeug fest
            endung = next((e for s, _n, e in FORMATE if s == self.format_schluessel), "")
            return name + endung
        return name

    def _ergebnis_fuellen(self) -> None:
        v = self.ergebnis_var
        info = self.aktuell
        if info is None:
            for var in v.values():
                var.set("")
            return
        if self.aktion_var.get() == AKTION_PRUEFEN:
            v["output"].set("-")
        else:
            v["output"].set(self._ziel_name())
        v["title_id"].set(info.title_id)
        v["content"].set(info.content_id)
        v["size"].set("ca. " + self._fmt(info.groesse))
        ziel = self.ziel_var.get().strip()
        frei = ""
        try:
            if ziel and os.path.isdir(ziel):
                frei = self._fmt(shutil.disk_usage(ziel).free)
        except OSError:
            frei = ""
        v["free"].set(frei)

    def _aktion_geaendert(self) -> None:
        """Der Anwender hat die Aktion gewaehlt: anwenden und merken."""
        self._merken(EINST_AKTION, self.aktion_var.get())
        self._aktion_anwenden()

    def _aktion_anwenden(self) -> None:
        """Kacheln, Ergebnis und Knoepfe zur Aktion nachziehen - ohne zu speichern (auch beim Oeffnen)."""
        for aktion, knopf in getattr(self, "_aktion_knoepfe", {}).items():
            try:
                knopf.configure(state="normal" if self._aktion_moeglich(aktion) else "disabled")
            except tk.TclError:
                pass
        self._kacheln_faerben()
        self._ergebnis_fuellen()
        self._knoepfe_pruefen()

    def _knoepfe_pruefen(self) -> None:
        laeuft = self._job is not None or self._uebergabe is not None
        try:
            self.start_knopf.configure(state="disabled" if (laeuft or self.aktuell is None) else "normal")
            self.abbrechen_knopf.configure(state="normal" if laeuft else "disabled")
            self.cover_knopf.configure(state="normal" if self.aktuell is not None else "disabled")
        except tk.TclError:
            pass

    def _fehler(self, text: str) -> None:
        self._protokoll(text)
        messagebox.showerror(self.t("ps5pkg.window_title"), text, parent=self.win)

    def _zu_umwandeln(self) -> None:
        self._seite_zeigen("umwandeln")

    def _alles_kopieren(self) -> None:
        zeilen = ["%s\t%s" % (self.tech.set(i, "eig"), self.tech.set(i, "wert")) for i in self.tech.get_children()]
        if zeilen:
            self.win.clipboard_clear()
            self.win.clipboard_append("\n".join(zeilen))
            self._status(self.t("ps5pkg.copied"))

    def _ziel_waehlen(self) -> None:
        ordner = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.choose_target_title"),
                                         initialdir=self.ziel_var.get() or None)
        if ordner:
            self.ziel_var.set(os.path.normpath(ordner))
            self._merken(EINST_ZIEL, self.ziel_var.get())
            self._ergebnis_fuellen()

    def _verlauf_leeren(self) -> None:
        try:
            self.protokoll.configure(state="normal")
            self.protokoll.delete("1.0", "end")
            self.protokoll.configure(state="disabled")
        except tk.TclError:
            pass

    def _ausgabe_oeffnen(self) -> None:
        ziel = self._z.get("ausgabe") or self.ziel_var.get().strip()
        if ziel and os.path.exists(ziel):
            try:
                if sys.platform == "win32":
                    os.startfile(ziel)  # noqa: S606
                else:
                    import subprocess
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ziel])
            except OSError as exc:
                self._protokoll(str(exc))

    # ------------------------------------------------------------------
    # Starten
    # ------------------------------------------------------------------
    def _starten(self) -> None:
        info = self.aktuell
        if info is None or self._job is not None or self._uebergabe is not None:
            return
        werkzeug = self._werkzeug()
        if not werkzeug:
            self._fehler(self.t("ps5pkg.err_no_tool"))
            return
        if not wz.dotnet_ordner():
            self._fehler(self.t("ps5pkg.err_no_dotnet"))
            return
        aktion = self.aktion_var.get()
        if aktion == AKTION_PRUEFEN:
            self._job_starten("pruefen", self._lauf_pruefen, info, "")
            return
        ziel = self.ziel_var.get().strip()
        if not ziel or not os.path.isdir(ziel):
            self._fehler(self.t("ps5pkg.err_no_target"))
            return
        self._merken(EINST_ZIEL, ziel)
        if aktion == AKTION_EXTRAHIEREN:
            ordner = os.path.join(ziel, anzeigename(info))
            if os.path.exists(ordner) and os.listdir(ordner):
                if not self.ueberschreiben_var.get():
                    messagebox.showinfo(self.t("ps5pkg.window_title"), self.t("ps5pkg.err_exists", pfad=ordner),
                                        parent=self.win)
                    return
                if not _haupt(self.g)._rmtree_force(ordner, ignore_errors=True) and os.path.exists(ordner):
                    self._fehler(self.t("ps5pkg.err_cannot_clear", pfad=ordner))
                    return
            self._job_starten("extrahieren", self._lauf_extrahieren, info, ordner)
            return
        if info.ist_ordner and self.format_schluessel == FORMAT_PAKET:
            self._bauen_starten(info, ziel)
            return
        # Umwandeln: ein Paket wird erst entpackt (Arbeitsordner), ein Spielordner geht gleich an Aufgabe 1
        if getattr(self.g, "is_running", False):
            messagebox.showinfo(self.t("ps5pkg.window_title"), self.t("ps5pkg.err_main_busy"), parent=self.win)
            return
        if info.ist_ordner:
            self._protokoll(self.t("ps5pkg.log_start_uebergabe", name=os.path.basename(info.pfad)))
            self.auftrag_var.set(self.t("ps5pkg.job_handoff"))
            self.balken["value"] = 0
            self.balken_gesamt["value"] = 50
            self._uebergabe = {"staging": "", "gesehen": False, "info": info}
            if not self._uebergeben(info.pfad):
                self._uebergabe = None
            self._knoepfe_pruefen()
            return
        arbeit = self._arbeitsordner()
        if not self._platz_reicht(arbeit, int(info.groesse * ENTPACKT_FAKTOR)):
            return
        staging = os.path.join(tempfile.mkdtemp(prefix="ps5conv_ps5pkg_", dir=arbeit), anzeigename(info))
        self._staging.append(os.path.dirname(staging))
        self._job_starten("umwandeln", self._lauf_extrahieren, info, staging)

    def _platz_reicht(self, ordner: str, noetig: int, nachfragen: bool = False) -> bool:
        """Genug freier Platz in ``ordner``? Knapp: Rueckfrage (``nachfragen``); weniger als gebraucht: Absage."""
        try:
            frei = int(shutil.disk_usage(ordner).free)
        except OSError:
            return True                   # nicht messbar - dann nicht im Weg stehen
        if frei >= noetig:
            return True
        self._protokoll(self.t("ps5pkg.err_space", ordner=ordner, frei=self._fmt(frei), noetig=self._fmt(noetig)))
        if nachfragen and frei >= noetig // 2:
            return bool(messagebox.askyesno(self.t("ps5pkg.window_title"), self.t(
                "ps5pkg.ask_space", ordner=ordner, frei=self._fmt(frei), noetig=self._fmt(noetig)), parent=self.win))
        messagebox.showerror(self.t("ps5pkg.window_title"), self.t(
            "ps5pkg.err_space", ordner=ordner, frei=self._fmt(frei), noetig=self._fmt(noetig)), parent=self.win)
        return False

    @staticmethod
    def _vorhandene_pakete(ziel: str, content_id: str) -> list[str]:
        """Pakete im Zielordner, die so heissen, wie das Werkzeug das neue nennen wird (``<Content-ID>-A..-V...pkg``)."""
        muster = re.compile(re.escape(content_id) + r"-A\d+-V\d+\.pkg$", re.IGNORECASE)
        try:
            return sorted(n for n in os.listdir(ziel) if muster.match(n))
        except OSError:
            return []

    def _param_neu_lesen(self, info: "wz.PaketInfo") -> bool:
        """Liest die ``param.json`` nach einer Reparatur neu und zieht Anzeige und Kennungen nach. ``False``, wenn die
        Kennungen danach nicht tragen."""
        import json
        try:
            with open(os.path.join(info.pfad, "sce_sys", "param.json"), encoding="utf-8-sig") as datei:
                param = json.load(datei)
        except (OSError, ValueError) as exc:
            logger.debug("param.json nach der Reparatur nicht lesbar: %s", exc)
            return False
        if not isinstance(param, dict):
            return False
        info.param = param
        info.titel = wz.titel_aus_param(param) or info.titel
        info.content_id = str(param.get("contentId", "") or "")
        info.title_id = str(param.get("titleId", "") or "")
        self._liste_fuellen(auswaehlen=info.pfad)
        self._paket_waehlen(info)
        return bool(wz.CONTENT_ID.match(info.content_id) and wz.TITLE_ID.match(info.title_id))

    def _bauen_starten(self, info: "wz.PaketInfo", ziel: str) -> None:
        """Baut aus einem Spielordner ein Debug-Paket: Kennungen und ``param.json`` pruefen, Platz pruefen, los."""
        if not (wz.CONTENT_ID.match(info.content_id) and wz.TITLE_ID.match(info.title_id)):
            self._fehler(self.t("ps5pkg.err_content_id", cid=info.content_id or "-", tid=info.title_id or "-"))
            return
        try:
            from ps5_validator.utils import param_check
            befund = param_check.pruefe_datei(os.path.join(info.pfad, "sce_sys", "param.json"),
                                              texte=self.g._param_check_texte())
            zeilen = befund.als_text(mit_hinweisen=False)
        except Exception as exc:  # noqa: BLE001 - die Pruefung ist eine Hilfe, kein Hindernis
            logger.debug("param.json-Pruefung vor dem Bauen: %s", exc)
            befund, zeilen = None, []
        if befund is not None and not befund.ok:
            for z in zeilen:
                self._protokoll(z)
            # Wie Aufgabe 1: erst die Reparatur anbieten (die alte Datei wird danebengelegt) - ein Paket mit
            # applicationDrmType "upgradable" bekommt sonst kein license.dat und zeigt an der Konsole ein Schloss.
            repariert = False
            try:
                repariert = bool(self.g._offer_repair_param_json(info.pfad, befund))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Reparatur der param.json: %s", exc)
            if repariert:
                if not self._param_neu_lesen(info):
                    self._fehler(self.t("ps5pkg.err_content_id", cid=info.content_id or "-", tid=info.title_id or "-"))
                    return
            elif not messagebox.askyesno(self.t("ps5pkg.ask_param_title"), self.t(
                    "ps5pkg.ask_param_text", befunde="\n".join(zeilen[:10])), parent=self.win):
                return
        # Ein Paket gleichen Namens im Ziel wird nur mit dem Haken ersetzt (das Werkzeug taete es still).
        vorhanden = self._vorhandene_pakete(ziel, info.content_id)
        if vorhanden and not self.ueberschreiben_var.get():
            messagebox.showinfo(self.t("ps5pkg.window_title"), self.t(
                "ps5pkg.err_exists_pkg", pfad=os.path.join(ziel, vorhanden[0])), parent=self.win)
            return
        # Das Werkzeug legt je nach Laufwerk eine Kopie des Spiels an und braucht Platz fuer das innere Abbild:
        # Der Arbeitsordner liegt deshalb im Zielordner (nicht auf dem oft kleinen Systemlaufwerk).
        if not self._platz_reicht(ziel, int(info.groesse * BAU_PLATZ_WARNUNG), nachfragen=True):
            return
        try:
            temp = tempfile.mkdtemp(prefix="ps5conv_pkgbau_", dir=ziel)
        except OSError:
            temp = tempfile.mkdtemp(prefix="ps5conv_pkgbau_", dir=self._arbeitsordner())
        self._staging.append(temp)
        self._bau = {"temp": temp, "vorher": set(os.listdir(ziel))}
        self._job_starten("bauen", self._lauf_bauen, info, ziel)

    def _job_starten(self, art: str, ziel_funktion, info: "wz.PaketInfo", ziel: str) -> None:
        self._abbruch = False
        self._job = {"art": art, "info": info, "ziel": ziel}
        with self._sperre:
            self._z.update({"prozent": 0.0, "fertig": None, "ausgabe": "", "gesamt": None})
        self.balken["value"] = 0
        self.balken_gesamt["value"] = 0
        self.schritt_var.set("0 %")
        text = {"pruefen": "ps5pkg.job_checking", "extrahieren": "ps5pkg.job_extracting",
                "umwandeln": "ps5pkg.job_extracting_for", "bauen": "ps5pkg.job_building"}[art]
        self.auftrag_var.set(self.t(text, name=anzeigename(info)))
        self._protokoll(self.t("ps5pkg.log_start_" + art, name=os.path.basename(info.pfad)))
        self._knoepfe_pruefen()
        threading.Thread(target=ziel_funktion, args=(info, ziel, art), daemon=True, name="ps5pkg-" + art).start()

    def _lauf_pruefen(self, info: "wz.PaketInfo", _ziel: str, _art: str) -> None:
        try:
            ergebnis = wz.pruefen(self._werkzeug(), info.pfad, abbruch=lambda: self._abbruch,
                                  popen_extra=self._popen_extra())
            for r in ergebnis.get("results", []):
                stufe = str(r.get("Level", ""))
                if stufe != "pass":
                    self._melden("[%s] %s: %s" % (stufe.upper(), r.get("Check", ""), r.get("Message", "")))
            # Ein abgeschlossener Pruefdurchlauf ist ein Ergebnis, kein Fehlschlag - auch mit Befunden.
            ende = {"ok": True, "befund": int(ergebnis.get("fail", 0)) > 0,
                    "text": self.t("ps5pkg.check_summary", ok=ergebnis.get("pass", 0), warn=ergebnis.get("warn", 0),
                                   fail=ergebnis.get("fail", 0))}
        except wz.Fehler as exc:
            ende = {"ok": False, "text": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket pruefen")
            ende = {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        with self._sperre:
            self._z["fertig"] = ende

    def _lauf_extrahieren(self, info: "wz.PaketInfo", ziel: str, art: str) -> None:
        def fortschritt(prozent: int, datei: str) -> None:
            with self._sperre:
                self._z["prozent"] = float(prozent)
                self._z["schritt_text"] = datei

        try:
            schluss = wz.extrahieren(self._werkzeug(), info.pfad, ziel, zeile=self._melden, fortschritt=fortschritt,
                                     abbruch=lambda: self._abbruch, popen_extra=self._popen_extra())
            ende = {"ok": True, "text": schluss, "ausgabe": ziel}
        except wz.Fehler as exc:
            ende = {"ok": False, "text": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket entpacken")
            ende = {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        with self._sperre:
            self._z["fertig"] = ende

    def _lauf_bauen(self, info: "wz.PaketInfo", ziel: str, art: str) -> None:
        """Arbeitsfaden: ``build`` aus dem Spielordner, danach ``validate`` am neuen Paket."""
        bau = getattr(self, "_bau", {}) or {}
        param = info.param if isinstance(info.param, dict) else {}

        def fortschritt(prozent: int, text: str) -> None:
            with self._sperre:
                self._z["prozent"] = float(prozent)
                self._z["gesamt"] = prozent / 2.0
                self._z["schritt_text"] = text

        try:
            pfad = wz.bauen(self._werkzeug(), info.pfad, ziel, content_id=info.content_id, title_id=info.title_id,
                            titel=info.titel, version=str(param.get("contentVersion", "") or "01.000.000"),
                            temp=bau.get("temp"), zeile=self._melden, fortschritt=fortschritt,
                            abbruch=lambda: self._abbruch, popen_extra=self._popen_extra())
        except wz.Fehler as exc:
            self._unfertiges_wegraeumen(ziel, bau)
            ende = {"ok": False, "text": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket bauen")
            self._unfertiges_wegraeumen(ziel, bau)
            ende = {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        else:
            with self._sperre:
                self._z["prozent"] = 100.0
                self._z["gesamt"] = 60.0
                self._z["schritt_text"] = self.t("ps5pkg.job_validating")
            self._melden(self.t("ps5pkg.job_validating"))
            try:
                erg = wz.pruefen(self._werkzeug(), pfad, abbruch=lambda: self._abbruch, popen_extra=self._popen_extra())
                for r in erg.get("results", []):
                    if str(r.get("Level", "")) != "pass":
                        self._melden("[%s] %s: %s" % (str(r.get("Level", "")).upper(), r.get("Check", ""), r.get("Message", "")))
                pruef = self.t("ps5pkg.check_summary", ok=erg.get("pass", 0), warn=erg.get("warn", 0),
                               fail=erg.get("fail", 0))
                befund = int(erg.get("fail", 0)) > 0
            except wz.Fehler as exc:
                pruef, befund = str(exc), True
            ende = {"ok": True, "text": pfad, "ausgabe": ziel, "pkg": pfad, "pruefung": pruef, "befund": befund}
        with self._sperre:
            self._z["fertig"] = ende

    @staticmethod
    def _unfertiges_wegraeumen(ziel: str, bau: dict) -> None:
        """Nach einem gescheiterten oder abgebrochenen Bau: was dabei neu im Zielordner entstand, ist unfertig."""
        vorher = bau.get("vorher")
        if vorher is None:
            return
        try:
            for name in set(os.listdir(ziel)) - set(vorher):
                pfad = os.path.join(ziel, name)
                if os.path.isfile(pfad):
                    os.remove(pfad)
        except OSError as exc:
            logger.debug("Unfertiges Paket nicht entfernbar: %s", exc)

    def _abbrechen(self) -> None:
        if self._job is not None:
            self._abbruch = True
            self._status(self.t("ps5pkg.status_cancelling"))
        elif self._uebergabe is not None:
            try:
                self.g._kill_task()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Abbruch der Aufgabe 1: %s", exc)

    # ------------------------------------------------------------------
    # Hand-off an Aufgabe 1
    # ------------------------------------------------------------------
    def _uebergeben(self, staging: str) -> bool:
        """Traegt den entpackten Ordner in Aufgabe 1 ein und startet sie."""
        g = self.g
        ziel = self.ziel_var.get().strip()
        try:
            g._set_mode_from_sidebar("pack_folder")
            g._batch_sources = []
            g.source_path.set(staging)
            g.dest_path.set(ziel)
            g.target_format.set(g._zielformat_label(self.format_schluessel, "pack_folder", staging))
            g._launch_task()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Uebergabe an Aufgabe 1")
            self._fehler(self.t("ps5pkg.err_handoff", grund=str(exc)))
            return False
        return True

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
            logger.exception("Takt des PS5-PKG-Fensters")
        try:
            self._takt_id = self.win.after(TAKT_MS, self._takt)
        except tk.TclError:
            self._takt_id = None

    def _takt_arbeiten(self) -> None:
        with self._sperre:
            zeilen, self._z["zeilen"] = self._z["zeilen"], []
            prozent = self._z["prozent"]
            datei = self._z["schritt_text"]
            fertig = self._z["fertig"]
            self._z["fertig"] = None
            gelesen, self._z["gelesen"] = self._z["gelesen"], []
            liest = self._z["lesen_laeuft"]
            gesamt = self._z.get("gesamt")
        for z in zeilen:
            self._protokoll(z)
        for paket_liste, waehlen in gelesen:
            self._gelesen_uebernehmen(paket_liste, waehlen)
        if gelesen and not liest:
            self._status(self.t("ps5pkg.status_idle"))
        if prozent is not None and self._job is not None:
            self.balken["value"] = prozent
            self.schritt_var.set("%d %%" % int(prozent))
            self.balken_gesamt["value"] = (gesamt if gesamt is not None
                                           else prozent if self._job["art"] != "umwandeln" else prozent / 2.0)
            if datei:
                self._status(datei)
        if fertig is not None and self._job is not None:
            self._job_beendet(fertig)
        if self._uebergabe is not None:
            self._uebergabe_beobachten()

    def _job_beendet(self, ende: dict) -> None:
        job, self._job = self._job, None
        art = job["art"]
        if not ende["ok"]:
            self.auftrag_var.set(self.t("ps5pkg.job_failed"))
            self._protokoll(self.t("ps5pkg.log_failed", grund=ende["text"]))
            self.balken_gesamt["value"] = 0
            if art in ("umwandeln", "bauen"):
                self._staging_raeumen()
            self._knoepfe_pruefen()
            return
        if art == "bauen":
            self._staging_raeumen()
            self.auftrag_var.set(self.t("ps5pkg.job_done_build", datei=os.path.basename(ende["pkg"])))
            self._protokoll(self.t("ps5pkg.log_built", pfad=ende["pkg"]))
            self._protokoll(("[BEFUND] " if ende.get("befund") else "[OK] ") + ende["pruefung"])
            self._protokoll(self.t("ps5pkg.build_note"))
            with self._sperre:
                self._z["ausgabe"] = job["ziel"]
            self.balken["value"] = 100
            self.balken_gesamt["value"] = 100
            self._knoepfe_pruefen()
            return
        if art == "pruefen":
            self.auftrag_var.set(ende["text"])
            self._protokoll(("[BEFUND] " if ende.get("befund") else "[OK] ") + ende["text"])
            self.balken["value"] = 100
            self.balken_gesamt["value"] = 100
            self._knoepfe_pruefen()
            return
        if art == "extrahieren":
            self.auftrag_var.set(self.t("ps5pkg.job_done_extract", ordner=job["ziel"]))
            self._protokoll(ende["text"])
            with self._sperre:
                self._z["ausgabe"] = job["ziel"]
            self.balken["value"] = 100
            self.balken_gesamt["value"] = 100
            self._knoepfe_pruefen()
            return
        # umwandeln: entpackt - nun Aufgabe 1
        self._protokoll(ende["text"])
        self.auftrag_var.set(self.t("ps5pkg.job_handoff"))
        self._uebergabe = {"staging": job["ziel"], "gesehen": False, "info": job["info"]}
        self.balken_gesamt["value"] = 50
        if not self._uebergeben(job["ziel"]):
            self._uebergabe = None
            self._staging_raeumen()
        self._knoepfe_pruefen()

    def _uebergabe_beobachten(self) -> None:
        laeuft = bool(getattr(self.g, "is_running", False))
        u = self._uebergabe
        if laeuft:
            u["gesehen"] = True
            return
        if not u["gesehen"]:
            # Aufgabe 1 hat gar nicht angefangen (Rueckfrage verneint, Pruefung gescheitert)
            u["wartezeit"] = u.get("wartezeit", 0) + 1
            if u["wartezeit"] * TAKT_MS < 4000:
                return
        ok = bool(getattr(self.g, "_last_task_ok", False)) and u["gesehen"]
        self._uebergabe = None
        if ok:
            self.auftrag_var.set(self.t("ps5pkg.job_done_convert"))
            self.balken["value"] = 100
            self.balken_gesamt["value"] = 100
            self._protokoll(self.t("ps5pkg.log_done_convert", name=self._ziel_name()))
        else:
            self.auftrag_var.set(self.t("ps5pkg.job_failed"))
            self._protokoll(self.t("ps5pkg.log_convert_not_done"))
        self._staging_raeumen()
        self._knoepfe_pruefen()

    def _staging_raeumen(self) -> None:
        haupt = _haupt(self.g)
        for ordner in self._staging:
            if os.path.isdir(ordner):
                try:
                    haupt._rmtree_force(ordner, ignore_errors=True)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Entpackordner %s nicht entfernbar: %s", ordner, exc)
        self._staging = [o for o in self._staging if os.path.isdir(o)]

    # ------------------------------------------------------------------
    # Schliessen
    # ------------------------------------------------------------------
    def _schliessen(self) -> None:
        if self._job is not None or self._uebergabe is not None:
            if not messagebox.askyesno(self.t("ps5pkg.window_title"), self.t("ps5pkg.close_running"), parent=self.win):
                return
            self._abbruch = True
        self.win.destroy()

    def _bei_zerstoerung(self, ereignis) -> None:
        if ereignis.widget is not self.win:
            return
        self._schliesst = True
        self._abbruch = True
        if self._takt_id is not None:
            try:
                self.win.after_cancel(self._takt_id)
            except tk.TclError:
                pass
        if self._uebergabe is None:
            self._staging_raeumen()
        self._cover = None
        for ordner in self._cover_ordner:
            try:
                _haupt(self.g)._rmtree_force(ordner, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
        if getattr(self.g, FENSTER_ATTRIBUT, None) is self:
            setattr(self.g, FENSTER_ATTRIBUT, None)


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int], vorgabe: str = "") -> Ps5PkgFenster:
    """Oeffnet das Fenster - oder holt das offene nach vorn."""
    vorhanden = getattr(gui, FENSTER_ATTRIBUT, None)
    if vorhanden is not None:
        try:
            if vorhanden.win.winfo_exists():
                vorhanden.win.deiconify()
                vorhanden.win.lift()
                if vorgabe:
                    vorhanden._pakete_hinzufuegen([p for p in vorgabe.split(os.pathsep) if p.strip()], waehlen=True)
                return vorhanden
        except tk.TclError:
            pass
    fenster = Ps5PkgFenster(gui, schrift, mono, pt, vorgabe)
    setattr(gui, FENSTER_ATTRIBUT, fenster)
    return fenster
