# -*- coding: utf-8 -*-
"""Das Fenster „PS4 PKG Dump & Image Converter“ (seit 07.10.2026, ersetzt „PS4 PKG -> OTA“ und „PS4 PKG -> ffpfsc“).

Eine schlichte Oberflaeche fuer alles, was man mit PS4-Paketen am PC macht:

* **Dump-Ordner** entpacken (Basis, Updates eingespielt, auf Wunsch DLC),
* **ffpfsc** oder **exFAT** bauen (ShadowMount+-Abbild),
* **Basis und Update zu einem Paket** zusammenfuehren,
* **Updates** online nachsehen und laden (Sonys Update-Server, nur PS4-Titel),
* Pakete **ueber das Netzwerk** an die Konsole senden (OTA).

Die Arbeit machen die Aufgaben aus ``ps5_validator.utils.ps4_abbild`` und ``ps4pkg_aufgaben`` in der
Warteschlange; dieses Modul zeigt nur an. **Faeden:** Arbeitsfaeden fassen nie ein Widget oder eine Tk-Variable
an; sie schreiben in die ``Aufgabe`` bzw. in ``self._z``, ein Takt im Fensterfaden (:meth:`_takt`) liest das
(wie in den anderen Fenstern, siehe ``project_tk_faden_variablen``). Texte kommen ueber ``gui._t``.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import orbispkg
from ps5_validator.utils import ps4_abbild as ab
from ps5_validator.utils import ps4_fortschritt, ps4_werkzeug
from ps5_validator.utils import ps4pkg_aufgaben as au
from ps5_validator.utils import ps4pkg_bibliothek as bib
from ps5_validator.utils import ps4pkg_ota as ota
from ps5_validator.utils import ps4pkg_updates as upd

logger = logging.getLogger("PS5Converter.ui.ps4_dump_image")

FENSTER_ATTRIBUT = "_ps4_dib_fenster"

#: Quellarten.
QUELLE_ORDNER = "pkg_dir"
QUELLE_DATEIEN = "pkg_file"
QUELLE_DUMP = "dump_dir"

#: Die Einstellungen dieses Fensters (``_load_setting``/``_save_setting``).
EINST_QUELLE = "ps4dib_quelle"
EINST_ART = "ps4dib_quelle_art"
EINST_ZIEL = "ps4dib_ziel"
EINST_FORMAT = "ps4dib_format"
EINST_STUFE = "ps4dib_stufe"
EINST_WORKER = "ps4dib_worker"
#: Die Netzwerk-Einstellungen behalten ihre Namen aus dem fruehren OTA-Fenster.
EINST_IP = "ps4ota_ip"
EINST_PORT = "ps4ota_port"
EINST_OTA_ART = "ps4ota_art"

ART_DPI = "dpi"
ART_RPI = "rpi"

#: So lang darf der Arbeitsordner hoechstens sein (Windows), bevor das Fenster auf einen kurzen Pfad im
#: Wurzelverzeichnis des Ziellaufwerks ausweicht; gilt die Zahl des Hauptmoduls (``_PS4FFPSC_MAX_ARBEITSPFAD``),
#: diese hier nur, wenn es sie nicht gibt.
MAX_ARBEITSPFAD = 45

#: Der Takt, in dem das Fenster die Warteschlange liest (Millisekunden).
TAKT_MS = 300


def _haupt(gui):
    """Das Hauptmodul (``__main__`` oder ``PS5ImageConverter_Pro_FINAL_revised``) - fuer seine Hilfsfunktionen."""
    return sys.modules.get(type(gui).__module__)


class Ps4DumpImageFenster:
    """Das Fenster. Eine Instanz je geoeffnetem Fenster."""

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int], vorgabe: str = "") -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self.pakete: list[bib.PkgEintrag] = []
        self.spiele: dict[str, ab.Spiel] = {}
        self._basis_wahl: dict[str, str] = {}      # Title-ID -> Pfad des gewaehlten Basispakets
        self._z: dict = {"scan_laeuft": False, "scan_abbruch": False, "scan_text": None, "scan_ergebnis": None,
                         "scan_fehler": "", "update": None, "ota_erkannt": None}
        self._schliesst = False
        self._takt_id = None
        self._batch: list[int] = []              # Kennungen der Aufgaben des laufenden Stapels
        self._batch_beginn = 0.0
        self._gemeldet: set[int] = set()         # Aufgaben, deren Ende schon im Protokoll steht
        self._gelesen: dict[int, int] = {}       # Aufgabe -> Zahl der schon gezeigten Protokollzeilen
        self._batch_hinweis: "dict | None" = None
        self._update_nach: "str | None" = None   # Title-ID, deren Update-Download gerade laeuft
        self.warteschlange = au.Warteschlange(bei_aenderung=None, uebersetzer=self.t)
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
        except Exception:  # noqa: BLE001
            logger.debug("Einstellung nicht gespeichert: %s", schluessel, exc_info=True)

    def _warnung(self, schluessel: str, **werte) -> None:
        messagebox.showwarning(self.t("ps4pkg.window_title"), self.t(schluessel, **werte), parent=self.win)

    def _protokoll(self, text: str) -> None:
        """Haengt eine Zeile an das Protokollfeld - nur im Fensterfaden."""
        if not self.protokoll.winfo_exists():
            return
        self.protokoll.insert("end", text.rstrip("\n") + "\n")
        self.protokoll.see("end")

    def _status(self, text: str) -> None:
        self.status_var.set(text)

    def _balken_setzen(self, wert: "float | None") -> None:
        """Der Balken samt Prozentzahl daneben. ``None`` = Dauer unbekannt (Suche): der Balken wandert, die Zahl zeigt „…“."""
        try:
            if wert is None:
                if not self._balken_unbestimmt:
                    self.balken.configure(mode="indeterminate")
                    self.balken.start()
                    self._balken_unbestimmt = True
                self.prozent_var.set("…")
                return
            if self._balken_unbestimmt:
                self.balken.stop()
                self.balken.configure(mode="determinate")
                self._balken_unbestimmt = False
            wert = max(0.0, min(100.0, float(wert)))
            self.balken.configure(value=wert)
            self.prozent_var.set("%d %%" % int(wert))
        except tk.TclError:
            pass

    def _frei(self) -> bool:
        """Laeuft nichts (weder Einlesen noch Aufgaben)?"""
        return not self._z["scan_laeuft"] and not self.warteschlange.offen

    def _menue(self) -> tk.Menu:
        return tk.Menu(self.win, tearoff=0, bg=self.c["bg_card"], fg=self.c["fg_primary"],
                       activebackground=self.c["fg_accent"], activeforeground=self.c["bg_main"],
                       font=(self.F, self.pt(9)))

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _bauen(self, vorgabe: str) -> None:
        g, t, c = self.g, self.t, self.c
        pw = g._pw
        F, pt = self.F, self.pt
        titel = t("ps4pkg.window_title")
        self.win = g._build_modern_toplevel(titel, 1000, 820, min_width=880, min_height=680)
        g._build_modern_header(self.win, titel, t("ps4pkg.subtitle"))
        koerper = tk.Frame(self.win, bg=c["bg_main"], padx=18)
        koerper.pack(fill="both", expand=True)

        self.art_var = tk.StringVar(value=str(self._einstellung(EINST_ART, QUELLE_ORDNER)))
        if self.art_var.get() not in (QUELLE_ORDNER, QUELLE_DATEIEN, QUELLE_DUMP):
            self.art_var.set(QUELLE_ORDNER)
        self.quelle_var = tk.StringVar(value=str(self._einstellung(EINST_QUELLE, "") or ""))
        if vorgabe:
            # Mehrere Pakete (aus der Bibliothek) kommen mit ``os.pathsep`` getrennt.
            self.art_var.set(QUELLE_DATEIEN)
            self.quelle_var.set(os.pathsep.join(os.path.normpath(p) for p in vorgabe.split(os.pathsep) if p.strip()))
        ziel = str(self._einstellung(EINST_ZIEL, "") or "")
        if not ziel and hasattr(g, "dest_path"):
            ziel = g.dest_path.get().strip()
        self.ziel_var = tk.StringVar(value=ziel)
        self._formate = {ab.FORMAT_DUMP: t("ps4dib.format_dump"), ab.FORMAT_FFPFSC: t("ps4dib.format_ffpfsc"),
                         ab.FORMAT_EXFAT: t("ps4dib.format_exfat"), ab.FORMAT_PKG: t("ps4dib.format_pkg")}
        gespeichert = str(self._einstellung(EINST_FORMAT, ab.FORMAT_FFPFSC))
        self.format_var = tk.StringVar(value=self._formate.get(gespeichert, self._formate[ab.FORMAT_FFPFSC]))
        self.stufe_var = tk.IntVar(value=self._zahl(self._einstellung(EINST_STUFE, 7), 7, 0, 9))
        self.worker_var = tk.IntVar(value=self._zahl(self._einstellung(EINST_WORKER, 0), max(1, (os.cpu_count() or 4) // 2),
                                                     1, max(1, os.cpu_count() or 4)))
        self.dlc_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=t("ps4pkg.status_idle"))

        # ── Quelle ──────────────────────────────────────────────────────
        tk.Label(koerper, text=t("ps4pkg.source_label"), font=(F, pt(9), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x", pady=(10, 4))
        art_reihe = tk.Frame(koerper, bg=c["bg_main"])
        art_reihe.pack(fill="x")
        for wert, schluessel in ((QUELLE_ORDNER, "ps4pkg.source_kind_dir"), (QUELLE_DATEIEN, "ps4pkg.source_kind_files"),
                                 (QUELLE_DUMP, "ps4pkg.source_kind_dump")):
            pw.Radiobutton(art_reihe, text=t(schluessel), value=wert, variable=self.art_var, font=(F, pt(9)),
                           command=self._quelle_gewaehlt,
                           bg=c["bg_main"], fg=c["fg_primary"], selectcolor=c["bg_card"],
                           activebackground=c["bg_main"], activeforeground=c["fg_primary"], highlightthickness=0,
                           bd=0).pack(side="left", padx=(0, 14))

        # ── Gefundene Spiele ────────────────────────────────────────────
        tk.Label(koerper, text=t("ps4pkg.games_label"), font=(F, pt(9), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x", pady=(10, 4))
        liste_rahmen = tk.Frame(koerper, bg=c["bg_main"])
        liste_rahmen.pack(fill="both", expand=True)
        spalten = ("title_id", "plattform", "titel", "version", "teile")
        self.liste = pw.Treeview(liste_rahmen, columns=spalten, show="headings", height=4, selectmode="extended")
        for spalte, breite in zip(spalten, (110, 80, 330, 90, 220)):
            self.liste.heading(spalte, text=t(f"ps4pkg.col_{spalte}"), anchor="w")
            self.liste.column(spalte, width=breite, anchor="w")
        self.liste.tag_configure("ps5", foreground=c["fg_warning"])
        self.liste.tag_configure("nicht_baubar", foreground=c["fg_secondary"])
        self.liste.pack(side="left", fill="both", expand=True)
        rolle = pw.Scrollbar(liste_rahmen, orient="vertical", command=self.liste.yview)
        rolle.pack(side="right", fill="y")
        self.liste.configure(yscrollcommand=rolle.set)

        # ── Ziel und Einstellungen ──────────────────────────────────────
        tk.Label(koerper, text=t("ps4pkg.output_label"), font=(F, pt(9), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x", pady=(10, 4))
        ziel_reihe = tk.Frame(koerper, bg=c["bg_main"])
        ziel_reihe.pack(fill="x")
        pw.Entry(ziel_reihe, textvariable=self.ziel_var, font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_primary"],
                 insertbackground=c["fg_primary"], relief="flat").pack(side="left", fill="x", expand=True, ipady=3)
        pw.Button(ziel_reihe, text="…", width=3, command=self._ziel_waehlen).pack(side="left", padx=(6, 0))

        einstell = tk.Frame(koerper, bg=c["bg_main"])
        einstell.pack(fill="x", pady=(8, 0))
        tk.Label(einstell, text=t("ps4pkg.format_label"), font=(F, pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"]).pack(side="left")
        self.format_box = pw.Combobox(einstell, textvariable=self.format_var, state="readonly", width=24,
                                      values=tuple(self._formate.values()), font=(F, pt(9)))
        self.format_box.pack(side="left", padx=(6, 18))
        tk.Label(einstell, text=t("ps4pkg.level_label"), font=(F, pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"]).pack(side="left")
        self.stufe_feld = pw.Spinbox(einstell, from_=0, to=9, textvariable=self.stufe_var, width=4, font=(F, pt(9)))
        self.stufe_feld.pack(side="left", padx=(6, 18))
        tk.Label(einstell, text=t("ps4pkg.workers_label"), font=(F, pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"]).pack(side="left")
        self.worker_feld = pw.Spinbox(einstell, from_=1, to=max(1, os.cpu_count() or 4), textvariable=self.worker_var,
                                      width=4, font=(F, pt(9)))
        self.worker_feld.pack(side="left", padx=(6, 18))
        dlc = pw.Checkbutton(einstell, text=t("ps4pkg.dlc_label"), variable=self.dlc_var, font=(F, pt(9)),
                             bg=c["bg_main"], fg=c["fg_warning"], selectcolor=c["bg_card"],
                             activebackground=c["bg_main"], activeforeground=c["fg_warning"], highlightthickness=0, bd=0)
        dlc.pack(side="left")
        tooltip = getattr(_haupt(g), "DelayedTooltip", None)
        if tooltip is not None:
            tooltip(dlc, t("ps4pkg.dlc_hint"), delay_ms=600, wraplength=420)

        # ── Fortschritt und Protokoll ───────────────────────────────────
        balken_reihe = tk.Frame(koerper, bg=c["bg_main"])
        balken_reihe.pack(fill="x", pady=(10, 3))
        self.prozent_var = tk.StringVar(value="0 %")
        tk.Label(balken_reihe, textvariable=self.prozent_var, width=6, anchor="e", font=(F, pt(10), "bold"),
                 bg=c["bg_main"], fg=c["fg_primary"]).pack(side="right", padx=(8, 0))
        self.balken = pw.Progressbar(balken_reihe, mode="determinate", maximum=100.0)
        self.balken.pack(side="left", fill="x", expand=True)
        self._balken_unbestimmt = False
        tk.Label(koerper, textvariable=self.status_var, font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                 anchor="w", wraplength=920, justify="left").pack(fill="x")
        self.protokoll = pw.Text(koerper, height=6, font=(self.M, pt(9)), bg=c["console_bg"], fg=c["console_fg"],
                                 relief="flat", insertbackground=c["console_fg"], wrap="word")
        self.protokoll.pack(fill="both", expand=True, pady=(6, 0))

        # ── Knopfleiste (zuerst unten gepackt, vor dem Koerper - sonst quetscht ihn die Mindesthoehe) ─────
        leiste = tk.Frame(self.win, bg=c["bg_main"], padx=16, pady=12)
        leiste.pack(side="bottom", fill="x", before=koerper)
        pw.Button(leiste, text=t("action.close"), command=self._schliessen).pack(side="right")
        self.abbrechen_knopf = pw.Button(leiste, text=t("action.cancel"), command=self._abbrechen)
        self.abbrechen_knopf.pack(side="right", padx=(0, 8))
        self.einlesen_knopf = pw.Button(leiste, text=t("ps4pkg.scan_button"), command=self._einlesen)
        self.einlesen_knopf.pack(side="left")
        self.start_knopf = pw.Button(leiste, text=t("ps4dib.start_button"), style="Accent.TButton", command=self._starten)
        self.start_knopf.pack(side="left", padx=(8, 0))
        self.update_knopf = pw.Button(leiste, text=t("ps4dib.btn_update"), command=self._update_online)
        self.update_knopf.pack(side="left", padx=(8, 0))
        self.senden_knopf = pw.Button(leiste, text=t("ps4dib.btn_senden"), command=self._senden)
        self.senden_knopf.pack(side="left", padx=(8, 0))
        self.mehr_knopf = pw.Button(leiste, text=t("ps4dib.btn_mehr"), command=self._mehr_menue)
        self.mehr_knopf.pack(side="left", padx=(8, 0))

        self.win.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.win.bind("<Destroy>", self._bei_zerstoerung, add="+")
        raster.spur_bis_zerstoert(self.win, self.format_var, self._format_geaendert)
        raster.spur_bis_zerstoert(self.win, self.art_var, self._formate_anpassen)
        self._formate_anpassen()
        # Eine Vorgabe (aus der Bibliothek) wird gleich eingelesen - der Anwender hat sie ja gerade gewaehlt.
        if vorgabe:
            self.win.after(200, self._einlesen)

    @staticmethod
    def _zahl(wert, vorgabe: int, kleinst: int, groesst: int) -> int:
        try:
            zahl = int(wert)
        except (TypeError, ValueError):
            return vorgabe
        return max(kleinst, min(groesst, zahl)) if zahl else vorgabe

    def _format_name(self) -> str:
        """Die Kennung des gewaehlten Formats."""
        wahl = self.format_var.get()
        for kennung, text in self._formate.items():
            if text == wahl:
                return kennung
        return ab.FORMAT_FFPFSC

    def _formate_anpassen(self, *_a) -> None:
        """Ein bereits entpacktes Spiel laesst sich nur zu einem Abbild bauen: Dump-Ordner und Paket stehen dann
        nicht zur Wahl (und ein gewaehltes wird zu ffpfsc)."""
        nur_abbild = self.art_var.get() == QUELLE_DUMP
        erlaubt = [text for kennung, text in self._formate.items() if not nur_abbild or kennung in ab.ABBILD_FORMATE]
        try:
            self.format_box.configure(values=tuple(erlaubt))
            if self.format_var.get() not in erlaubt:
                self.format_var.set(self._formate[ab.FORMAT_FFPFSC])
        except (tk.TclError, AttributeError):
            pass

    def _quelle_gewaehlt(self) -> None:
        """Ein Druck auf einen der drei Quellknoepfe oeffnet gleich die Wahl dazu (Ordner, Dateien, Spielordner)."""
        self._quelle_waehlen()

    def _format_geaendert(self, *_a) -> None:
        """Merkt das Format. Stufe und Worker gelten nur fuer ffpfsc (Worker auch fuer Pakete); die uebrigen
        Formate ignorieren sie einfach - die Drehknoepfe lassen sich nicht sperren."""
        self._merken(EINST_FORMAT, self._format_name())

    # ------------------------------------------------------------------
    # Quelle und Ziel waehlen
    # ------------------------------------------------------------------
    def _quelle_waehlen(self) -> None:
        art = self.art_var.get()
        if art == QUELLE_DATEIEN:
            pfade = filedialog.askopenfilenames(title=self.t("ps4pkg.choose_files"),
                                                filetypes=[(self.t("ps4pkg.filetype_pkg"), "*.pkg")], parent=self.win)
            if pfade:
                self._quelle_uebernehmen(os.pathsep.join(os.path.normpath(p) for p in pfade))
            return
        ordner = filedialog.askdirectory(title=self.t("ps4dib.choose_dump" if art == QUELLE_DUMP else "ps4pkg.choose_dir"),
                                         initialdir=self.g._get_source_dialog_initial_dir() or None, parent=self.win)
        if ordner:
            self._quelle_uebernehmen(os.path.normpath(ordner))

    def _quelle_uebernehmen(self, wert: str) -> None:
        """Die gewaehlte Quelle gilt gleich und wird eingelesen - ein Eingabefeld dafuer gibt es nicht mehr."""
        self.quelle_var.set(wert)
        self._protokoll(self.t("ps4dib.quelle_gewaehlt", pfad=wert.replace(os.pathsep, "; ")))
        self._einlesen()

    def _ziel_waehlen(self) -> None:
        ordner = filedialog.askdirectory(title=self.t("ps4pkg.choose_output"), parent=self.win)
        if ordner:
            self.ziel_var.set(os.path.normpath(ordner))

    def _quellen(self) -> "list[str] | None":
        """Die gewaehlten Quellen als Liste; ``None`` (mit Warnung) bei ungueltiger Eingabe."""
        eingabe = self.quelle_var.get().strip()
        art = self.art_var.get()
        pfade = [p.strip() for p in eingabe.split(os.pathsep) if p.strip()] if art == QUELLE_DATEIEN else (
            [eingabe] if eingabe else [])
        gueltig = [p for p in pfade if (os.path.isfile(p) if art == QUELLE_DATEIEN else os.path.isdir(p))]
        if not gueltig:
            self._warnung("ps4pkg.no_source")
            return None
        return gueltig

    # ------------------------------------------------------------------
    # Einlesen
    # ------------------------------------------------------------------
    def _zwischenspeicher(self) -> "bib.Zwischenspeicher":
        try:
            from ps5_validator.utils.einstellungen import konfigurationsordner
            return bib.Zwischenspeicher(os.path.join(konfigurationsordner(), "ps4dib_sammlung.json"))
        except Exception:  # noqa: BLE001
            return bib.Zwischenspeicher("")

    def _einlesen(self) -> None:
        if not self._frei():
            return
        quellen = self._quellen()
        if quellen is None:
            return
        art = self.art_var.get()
        self._merken(EINST_ART, art)
        self._merken(EINST_QUELLE, self.quelle_var.get().strip())
        self.liste.delete(*self.liste.get_children())
        self.spiele = {}
        self.pakete = []
        if art == QUELLE_DUMP:
            # Ein entpacktes Spiel: nur die param.sfo lesen - kein Faden noetig.
            spiel = ab.spiel_aus_dump(quellen[0])
            if spiel is None:
                self._status(self.t("ps4dib.dump_ohne_sfo"))
                self._protokoll(self.t("ps4dib.dump_ohne_sfo"))
                return
            self.spiele[spiel.title_id] = spiel
            self._liste_fuellen(auswaehlen=spiel.title_id)
            self._status(self.t("ps4pkg.status_found", count=1))
            return
        self._z.update(scan_laeuft=True, scan_abbruch=False, scan_text=None, scan_ergebnis=None, scan_fehler="")
        zwischen = self._zwischenspeicher()
        self._status(self.t("ps4pkg.status_scanning"))
        self._balken_setzen(None)
        eingabe, art_fuer_sicht = self.quelle_var.get().strip(), art

        def arbeit() -> None:
            try:
                erg = bib.einlesen(
                    quellen, fortschritt=lambda a, g, d: self._z.__setitem__("scan_text", ("lese", a, g, d)),
                    suche_fortschritt=lambda n, o: self._z.__setitem__("scan_text", ("suche", n, 0, o)),
                    abbruch=lambda: self._z.get("scan_abbruch", False), zwischenspeicher=zwischen)
                sicht = None
                try:
                    sicht = self.g._ps4ffpsc_quellen_sichten(eingabe, art_fuer_sicht)
                except Exception:  # noqa: BLE001 - nur ein Hinweis
                    logger.debug("PS5-Pakete nicht gezaehlt", exc_info=True)
                self._z["scan_ergebnis"] = (erg, sicht)
            except Exception as exc:  # noqa: BLE001
                logger.exception("PS4-Einlesen fehlgeschlagen")
                self._z["scan_fehler"] = str(exc)
            finally:
                self._z["scan_laeuft"] = False
                self._z["scan_fertig"] = True

        threading.Thread(target=arbeit, daemon=True, name="ps4dib-einlesen").start()

    def _scan_fertig(self) -> None:
        self._z["scan_fertig"] = False
        if self._z["scan_fehler"]:
            meldung = self.t("ps4pkg.status_scan_crashed", error=self._z["scan_fehler"])
            self._status(meldung)
            self._protokoll(meldung)
            self._balken_setzen(0.0)
            return
        ergebnis = self._z["scan_ergebnis"]
        if not ergebnis:
            self._balken_setzen(0.0)
            return
        self._balken_setzen(100.0)
        eintraege, sicht = ergebnis
        self.pakete = list(eintraege)
        if sicht and sicht.get("ps5"):
            self._protokoll(self.t("ps4pkg.ps5_packages", anzahl=len(sicht["ps5"])))
            for name in sicht["ps5"][:12]:
                self._protokoll("    %s" % name)
            if len(sicht["ps5"]) > 12:
                self._protokoll(self.t("ps4pkg.and_more", anzahl=len(sicht["ps5"]) - 12))
        unlesbar = [e for e in self.pakete if not e.lesbar and not (sicht and e.pfad in (sicht.get("ps5") or []))]
        # "Kennung fehlt" heisst: kein PS4-Paket (meist PS5 oder DLC-Freischalter) - kein Fehler, nur uebersprungen.
        fremd = [e for e in unlesbar if "kein PS4-Paket" in (e.fehler or "")]
        defekt = [e for e in unlesbar if e not in fremd]
        if fremd:
            self._protokoll(self.t("ps4dib.nicht_ps4_header", anzahl=len(fremd)))
            for e in fremd[:12]:
                self._protokoll("    %s" % e.datei)
            if len(fremd) > 12:
                self._protokoll(self.t("ps4pkg.and_more", anzahl=len(fremd) - 12))
        if defekt:
            self._protokoll(self.t("ps4pkg.rejected_header", anzahl=len(defekt)))
            for e in defekt[:12]:
                self._protokoll(self.t("ps4pkg.rejected_entry", name=e.datei, grund=e.fehler or "?"))
        self._gruppieren()
        self._status(self.t("ps4pkg.status_found", count=len(self.spiele)))

    # ------------------------------------------------------------------
    # Mehrere Basispakete: der Anwender waehlt
    # ------------------------------------------------------------------
    def _basen_klaeren(self, spiele: "list[ab.Spiel]") -> bool:
        """Fragt bei jedem Titel mit mehreren Basispaketen, welches gelten soll (einmal je Titel). ``False`` = Abbruch."""
        for s in spiele:
            if len(s.basen) > 1 and not s.basis_gewaehlt:
                if not self._basis_waehlen(s):
                    return False
        return True

    def _basis_menue(self) -> None:
        for s in self._gewaehlt():
            if len(s.basen) > 1:
                if self._basis_waehlen(s):
                    self._liste_fuellen(auswaehlen=s.title_id)
                return

    def _basis_waehlen(self, spiel: "ab.Spiel") -> bool:
        """Dialog mit allen Basispaketen des Titels; ``True``, wenn eines gewaehlt wurde."""
        t, c, F, pt = self.t, self.c, self.F, self.pt
        pw = self.g._pw
        dlg = self.g._build_modern_toplevel(t("ps4dib.basis_titel"), 760, 400, min_width=620, min_height=300)
        self.g._build_modern_header(dlg, t("ps4dib.basis_titel"),
                                    t("ps4dib.basis_untertitel", titel=spiel.titel or spiel.title_id,
                                      title_id=spiel.title_id))
        rahmen = tk.Frame(dlg, bg=c["bg_main"], padx=20, pady=8)
        rahmen.pack(fill="both", expand=True)
        aktuell = next((i for i, b in enumerate(spiel.basen) if b is spiel.basis), len(spiel.basen) - 1)
        wahl = tk.StringVar(value=str(aktuell))
        for i, b in enumerate(spiel.basen):
            text = t("ps4dib.basis_zeile", fassung=b.app_ver or b.version or "-",
                     groesse=self.g._fmt_bytes(b.groesse) if b.groesse else "-", datei=b.datei or b.pfad)
            pw.Radiobutton(rahmen, text=text, value=str(i), variable=wahl, font=(F, pt(9)),
                           bg=c["bg_main"], fg=c["fg_primary"], selectcolor=c["bg_card"],
                           activebackground=c["bg_main"], activeforeground=c["fg_primary"],
                           highlightthickness=0, bd=0).pack(anchor="w", pady=3)
        ergebnis = {"ok": False}

        def uebernehmen() -> None:
            spiel.basis_setzen(spiel.basen[int(wahl.get())])
            self._basis_wahl[spiel.title_id] = spiel.basis.pfad
            ergebnis["ok"] = True
            dlg.destroy()

        knoepfe = tk.Frame(rahmen, bg=c["bg_main"])
        knoepfe.pack(fill="x", pady=(14, 0))
        pw.Button(knoepfe, text=t("ps4dib.basis_nehmen"), style="Accent.TButton", command=uebernehmen).pack(side="left")
        pw.Button(knoepfe, text=t("action.cancel"), command=dlg.destroy).pack(side="right")
        dlg.transient(self.win)
        dlg.grab_set()
        self.win.wait_window(dlg)
        return ergebnis["ok"]

    def _gruppieren(self) -> None:
        self.spiele = {s.title_id: s for s in ab.spiele_gruppieren(self.pakete)}
        for s in self.spiele.values():
            gemerkt = self._basis_wahl.get(s.title_id)
            if gemerkt and len(s.basen) > 1:
                for b in s.basen:
                    if os.path.normcase(b.pfad) == os.path.normcase(gemerkt):
                        s.basis_setzen(b)
            if s.mehrere_basen:
                self._protokoll(self.t("ps4dib.mehrere_basen", title_id=s.title_id,
                                       fassung=(s.basis.app_ver if s.basis else "-")))
            if s.basis is None:
                self._protokoll(self.t("ps4dib.ohne_basis_hinweis", title_id=s.title_id))
        self._liste_fuellen()

    def _liste_fuellen(self, auswaehlen: str = "") -> None:
        gemerkt = auswaehlen or (self.liste.selection()[0] if self.liste.selection() else "")
        self.liste.delete(*self.liste.get_children())
        for s in sorted(self.spiele.values(), key=lambda x: (x.titel.lower(), x.title_id)):
            plattform = ps4_werkzeug.plattform(s.title_id)
            anzeige = {"ps4": "PS4", "ps5": "PS5"}.get(plattform, self.t("ps4pkg.platform_unknown"))
            if s.dump_ordner:
                teile = self.t("ps4dib.teile_dump")
            else:
                teile = self.t("ps4pkg.parts", patches=len(s.updates), dlc=len(s.zusaetze))
                if len(s.basen) > 1:
                    teile = self.t("ps4dib.basen_zaehler", anzahl=len(s.basen)) + ", " + teile
                if not s.baubar:
                    teile = self.t("ps4pkg.not_buildable") + " - " + teile
            tags = ("ps5",) if plattform == "ps5" else (() if s.baubar else ("nicht_baubar",))
            self.liste.insert("", "end", iid=s.title_id, tags=tags,
                              values=(s.title_id, anzeige, s.titel, s.version, teile))
        if gemerkt and self.liste.exists(gemerkt):
            self.liste.selection_set(gemerkt)
        elif self.liste.get_children():
            self.liste.selection_set(self.liste.get_children()[0])

    # ------------------------------------------------------------------
    # Starten
    # ------------------------------------------------------------------
    def _gewaehlt(self) -> list[ab.Spiel]:
        return [self.spiele[i] for i in self.liste.selection() if i in self.spiele]

    def _arbeitsbasis(self, ziel: str) -> str:
        """Wo der Arbeitsordner hin soll: beim Ziel; unter Windows bei zu langem Pfad im Wurzelverzeichnis."""
        basis = os.path.join(ziel, "ps4dib_arbeit")
        haupt = _haupt(self.g)
        kurz = getattr(haupt, "_ps4ffpsc_kurzer_arbeitsordner", None)
        grenze = int(getattr(haupt, "_PS4FFPSC_MAX_ARBEITSPFAD", MAX_ARBEITSPFAD))
        if sys.platform == "win32" and len(basis) > grenze and callable(kurz):
            ausweich = kurz(ziel)
            self._protokoll(self.t("ps4pkg.short_workdir", laenge=len(basis), pfad=ausweich))
            return ausweich
        return basis

    def _starten(self) -> None:
        if not self._frei():
            return
        t = self.t
        gewaehlt = self._gewaehlt()
        if not gewaehlt:
            self._warnung("ps4pkg.no_game")
            return
        ziel = self.ziel_var.get().strip()
        if not ziel or not os.path.isdir(ziel):
            self._warnung("ps4pkg.no_output")
            return
        try:
            stufe = int(self.stufe_var.get())
            worker = int(self.worker_var.get())
        except (tk.TclError, ValueError):
            self._warnung("ps4pkg.bad_number")
            return
        if not self._basen_klaeren(gewaehlt):
            return
        kennung = self._format_name()
        mit_dlc = bool(self.dlc_var.get()) and kennung in (ab.FORMAT_FFPFSC, ab.FORMAT_EXFAT, ab.FORMAT_DUMP)
        for s in gewaehlt:
            fehler = self._pruefe_spiel(s, kennung)
            if fehler:
                messagebox.showwarning(t("ps4pkg.window_title"), fehler, parent=self.win)
                return
        if mit_dlc and kennung in ab.ABBILD_FORMATE and not messagebox.askyesno(
                t("ps4pkg.window_title"), t("ps4pkg.dlc_confirm"), parent=self.win):
            return
        self._merken(EINST_ZIEL, ziel)
        self._merken(EINST_STUFE, stufe)
        self._merken(EINST_WORKER, worker)
        haupt = _haupt(self.g)
        if kennung in ab.ABBILD_FORMATE and haupt is not None and not haupt._ps4ffpsc_wurzel():
            messagebox.showerror(t("ps4pkg.window_title"), t("ps4pkg.missing_tool"), parent=self.win)
            return
        self._batch, self._gemeldet, self._gelesen = [], set(), {}
        self._batch_beginn = time.monotonic()
        self._balken_setzen(0.0)
        hinweis_texte = self.g._modul_texte(ps4_werkzeug.MELDUNGEN, "ps4werkzeug.")
        arbeit = self._arbeitsbasis(ziel) if kennung in ab.ABBILD_FORMATE else ""
        if arbeit:
            os.makedirs(arbeit, exist_ok=True)
        for s in gewaehlt:
            titel = t("ps4dib.aufg_titel", titel=s.titel or s.title_id, format=self._formate[kennung])
            if kennung == ab.FORMAT_DUMP:
                ordner = os.path.join(ziel, s.title_id)
                a = self.warteschlange.hinzufuegen(
                    "dump", titel, lambda a, s=s, o=ordner: ab.arbeit_dump(a, s, o, t, mit_dlc=mit_dlc),
                    quelle=s.title_id, ziel=ordner)
            elif kennung == ab.FORMAT_PKG:
                a = self.warteschlange.hinzufuegen(
                    "pkg", titel, lambda a, s=s: ab.arbeit_pkg_zusammen(a, s, ziel, t, arbeiter=worker),
                    quelle=s.title_id, ziel=ziel)
            else:
                a = self.warteschlange.hinzufuegen(
                    "abbild", titel,
                    lambda a, s=s, k=kennung: ab.arbeit_abbild(
                        a, s, ziel, k, t, lauf=self._lauf_fuer(a), arbeitsordner=arbeit, stufe=stufe, worker=worker,
                        mit_dlc=mit_dlc, hinweis_texte=hinweis_texte),
                    quelle=s.title_id, ziel=ziel)
            self._batch.append(a.kennung)
            self._protokoll(t("ps4dib.log_aufgabe_neu", titel=titel))
        if kennung in ab.ABBILD_FORMATE:
            # Der Hinweis zum Ablageort kommt waehrend der Umwandlung, wenn der Anwender auf den Balken schaut.
            self._batch_hinweis = {"gezeigt": set(), "laeuft": False, "fenster": None, "fertig": False, "uhr": None}
            self.g._ps4_hinweis_stand = self._batch_hinweis
            self.g._ps4_hinweis_zeit_starten(self.win)
        self._knoepfe_pruefen()

    def _lauf_fuer(self, aufgabe: au.Aufgabe):
        """Ein ``lauf`` fuer PS4 FFPFSC, der den Prozess der Aufgabe zum Abbrechen ablegt."""
        def lauf(argumente, *, arbeitsordner, zeile_callback, fortschritt_callback=None, prozess_ablage=None, **rest):
            return self.g._ps4ffpsc_lauf(argumente, arbeitsordner=arbeitsordner, zeile_callback=zeile_callback,
                                         fortschritt_callback=fortschritt_callback, prozess_ablage=prozess_ablage,
                                         **rest)
        return lauf

    def _pruefe_spiel(self, s: ab.Spiel, kennung: str) -> str:
        """Ein Satz, warum dieses Spiel mit diesem Format nicht geht - oder ``""``."""
        t = self.t
        if ps4_werkzeug.plattform(s.title_id) == "ps5":
            return t("ps4pkg.is_ps5_title", title_id=s.title_id)
        if not s.baubar:
            return t("ps4dib.ohne_basis", title_id=s.title_id)
        if s.dump_ordner and kennung not in ab.ABBILD_FORMATE:
            return t("ps4dib.dump_nur_abbild")
        if kennung == ab.FORMAT_PKG and not s.updates:
            return t("ps4dib.pkg_ohne_update", title_id=s.title_id)
        if kennung in (ab.FORMAT_DUMP, ab.FORMAT_PKG) and not orbispkg.verfuegbar():
            return t("ps4dib.ohne_orbis", system=sys.platform)
        return ""

    # ------------------------------------------------------------------
    # Abbrechen und Schliessen
    # ------------------------------------------------------------------
    def _abbrechen(self) -> None:
        if self._z["scan_laeuft"]:
            self._z["scan_abbruch"] = True
            self._status(self.t("ps4pkg.status_cancelling"))
        if self.warteschlange.offen:
            self.warteschlange.alle_abbrechen()
            self._status(self.t("ps4pkg.status_cancelling"))

    def _schliessen(self) -> None:
        if not self._frei():
            if not messagebox.askyesno(self.t("ps4pkg.window_title"), self.t("ps4pkg.abort_confirm"),
                                       parent=self.win, default="no"):
                return
            self._z["scan_abbruch"] = True
            self.warteschlange.alle_abbrechen()
        self._schliesst = True
        self._hinweis_aufraeumen()
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _bei_zerstoerung(self, ereignis) -> None:
        if ereignis.widget is not self.win:
            return
        self._schliesst = True
        self._z["scan_abbruch"] = True
        if self._takt_id is not None:
            try:
                self.win.after_cancel(self._takt_id)
            except (tk.TclError, ValueError):
                pass
            self._takt_id = None
        if getattr(self.g, FENSTER_ATTRIBUT, None) is self:
            setattr(self.g, FENSTER_ATTRIBUT, None)

    def _hinweis_aufraeumen(self) -> None:
        try:
            self.g._ps4_hinweis_aufraeumen(self._batch_hinweis)
        except Exception:  # noqa: BLE001
            logger.debug("Hinweis nicht aufgeraeumt", exc_info=True)

    # ------------------------------------------------------------------
    # Der Takt: liest Warteschlange und Einlesen, zeigt Balken, Status und Protokoll
    # ------------------------------------------------------------------
    def _takt(self) -> None:
        self._takt_id = None
        if self._schliesst:
            return
        try:
            if not self.win.winfo_exists():
                return
            self._takt_arbeiten()
        except tk.TclError:
            return
        except Exception:  # noqa: BLE001 - ein Fehler in der Anzeige darf den Takt nie beenden
            logger.exception("Takt von PS4 PKG Dump & Image Converter")
        try:
            self._takt_id = self.win.after(TAKT_MS, self._takt)
        except tk.TclError:
            self._takt_id = None

    def _takt_arbeiten(self) -> None:
        if self._z["scan_laeuft"]:
            roh = self._z.get("scan_text")
            if roh:
                art, a, g, d = roh
                if art == "suche":
                    self._status(self.t("ps4dib.suche", anzahl=a))
                    self._balken_setzen(None)
                elif g:
                    self._status(self.t("ps4dib.lese_paket", aktuell=a, gesamt=g, datei=d))
                    self._balken_setzen(100.0 * a / g)
        if self._z.get("scan_fertig"):
            self._scan_fertig()
        self._aufgaben_anzeigen()
        self._update_ergebnis()
        self._ota_ergebnis()
        self._knoepfe_pruefen()

    def _knoepfe_pruefen(self) -> None:
        frei = self._frei()
        for knopf in (self.einlesen_knopf, self.start_knopf, self.update_knopf, self.senden_knopf, self.mehr_knopf):
            try:
                knopf.state(["!disabled"] if frei else ["disabled"])
            except tk.TclError:
                pass
        try:
            self.abbrechen_knopf.state(["!disabled"] if not frei else ["disabled"])
        except tk.TclError:
            pass

    def _aufgaben_anzeigen(self) -> None:
        schnappschuss = {a.kennung: a for a in self.warteschlange.schnappschuss()}
        stapel = [schnappschuss[k] for k in self._batch if k in schnappschuss]
        # Neue Protokollzeilen aller Aufgaben des Stapels.
        for a in stapel:
            gesehen = self._gelesen.get(a.kennung, 0)
            if len(a.protokoll) > gesehen:
                for zeile in a.protokoll[gesehen:]:
                    self._protokoll(zeile)
                self._gelesen[a.kennung] = len(a.protokoll)
        if stapel:
            self._stapel_anzeigen(stapel)
        # Der Update-Download steht ausserhalb des Stapels.
        for a in schnappschuss.values():
            if a.art == "update" and a.status in au.ENDZUSTAENDE and a.kennung not in self._gemeldet:
                self._gemeldet.add(a.kennung)
                self._update_geladen(a)
            elif a.art in ("ota", "pruefen") and a.status in au.ENDZUSTAENDE and a.kennung not in self._gemeldet:
                self._gemeldet.add(a.kennung)
                self._kurz_beendet(a)
            elif a.art in ("ota", "pruefen", "update") and a.status == au.LAEUFT:
                self._kurz_laeuft(a)
        # Fenster kennt Aufgaben, die nicht im Stapel stehen, nur kurz - der Stapel bestimmt den Balken.

    def _stapel_anzeigen(self, stapel: "list[au.Aufgabe]") -> None:
        t = self.t
        fertig = [a for a in stapel if a.status in au.ENDZUSTAENDE]
        for a in fertig:
            if a.kennung not in self._gemeldet:
                self._gemeldet.add(a.kennung)
                self._aufgabe_beendet(a)
        laeuft = next((a for a in stapel if a.status == au.LAEUFT), None)
        prozent = sum(100.0 if a.status in au.ENDZUSTAENDE else a.prozent for a in stapel) / len(stapel)
        self._balken_setzen(prozent)
        if self._batch_hinweis is not None and self.g._ps4_hinweis_faellig(prozent):
            self.g._ps4_hinweis_zeigen(self.win)
        if laeuft is not None:
            verstrichen = time.monotonic() - self._batch_beginn
            rest = ps4_fortschritt.rest_sekunden(verstrichen, prozent)
            self._status(t("ps4dib.status_gesamt", titel=laeuft.titel, text=laeuft.text or "…", prozent=int(prozent),
                           vergangen=ps4_fortschritt.dauer_text(verstrichen),
                           rest=ps4_fortschritt.dauer_text(rest) if rest is not None else t("ps4pkg.zeit_berechnet")))
        elif len(fertig) == len(stapel):
            self._stapel_fertig(stapel)

    def _aufgabe_beendet(self, a: au.Aufgabe) -> None:
        t = self.t
        if a.status == au.FERTIG:
            self._protokoll(t("ps4dib.log_ok", titel=a.titel, pfad=a.ergebnis or a.ziel))
            self.g._append_to_log(t("ps4pkg.log_done", title=a.titel, path=a.ergebnis or a.ziel))
        elif a.status == au.ABGEBROCHEN:
            self._protokoll(t("ps4dib.log_abgebrochen", titel=a.titel))
        else:
            self._protokoll(t("ps4dib.log_fehler", titel=a.titel, grund=a.fehler))
            self.g._append_to_log(t("ps4pkg.log_failed", title=a.titel, code=0) + "\n")
            for zeile in a.protokoll[-12:]:
                self.g._append_to_log("    %s\n" % zeile)

    def _stapel_fertig(self, stapel: "list[au.Aufgabe]") -> None:
        t = self.t
        self._hinweis_aufraeumen()
        self._batch_hinweis = None
        self._batch = []
        fehler = sum(1 for a in stapel if a.status == au.FEHLER)
        abgebrochen = sum(1 for a in stapel if a.status == au.ABGEBROCHEN)
        if abgebrochen and not fehler:
            self._status(t("ps4pkg.status_cancelled"))
        elif fehler:
            self._status(t("ps4dib.status_mit_fehlern", fehler=fehler, gesamt=len(stapel)))
        else:
            ziel = stapel[-1].ergebnis or stapel[-1].ziel
            self._balken_setzen(100.0)
            self._status(t("ps4pkg.status_done", path=ziel))

    # ------------------------------------------------------------------
    # Updates online
    # ------------------------------------------------------------------
    def _update_online(self) -> None:
        if not self._frei():
            return
        gewaehlt = self._gewaehlt()
        if not gewaehlt:
            self._warnung("ps4pkg.no_game")
            return
        s = gewaehlt[0]
        if upd.ist_ps5(s.title_id):
            self._status(self.t("ps4ota.update_ps5_hinweis"))
            self._protokoll(self.t("ps4ota.update_ps5_hinweis"))
            return
        if not upd.title_id_gueltig(s.title_id):
            self._warnung("ps4ota.update_keine_title_id")
            return
        self._status(self.t("ps4ota.update_frage", title_id=s.title_id))
        self._z["update"] = None
        self._z["update_laeuft"] = True
        self._knoepfe_pruefen()
        title_id = s.title_id

        def arbeit() -> None:
            try:
                self._z["update"] = (title_id, upd.nachsehen(title_id), "")
            except upd.UpdateFehler as fehler:
                self._z["update"] = (title_id, None, fehler.schluessel + ": " + fehler.text)
            except ValueError as fehler:
                self._z["update"] = (title_id, None, str(fehler))
            finally:
                self._z["update_laeuft"] = False

        threading.Thread(target=arbeit, daemon=True, name="ps4dib-update").start()

    def _update_ergebnis(self) -> None:
        roh = self._z.get("update")
        if not roh:
            return
        self._z["update"] = None
        title_id, info, fehler = roh
        t = self.t
        if fehler:
            self._status(t("ps4ota.update_fehler", fehler=fehler))
            self._protokoll(t("ps4ota.log_update_fehler", title_id=title_id, fehler=fehler))
            return
        if info is None:
            self._status(t("ps4ota.update_keins", title_id=title_id))
            self._protokoll(t("ps4ota.log_update_keins", title_id=title_id))
            return
        spiel = self.spiele.get(title_id)
        lokal = (spiel.neuestes_update.app_ver if spiel and spiel.neuestes_update else
                 (spiel.basis.app_ver if spiel and spiel.basis else ""))
        self._protokoll(t("ps4ota.log_update_gefunden", title_id=title_id, version=info.version))
        zeilen = [t("ps4ota.update_online_version", version=info.version or "-"),
                  t("ps4ota.update_online_groesse", groesse=self.g._fmt_bytes(info.groesse) if info.groesse else "-"),
                  t("ps4ota.update_online_system", system=info.firmware_text or "-"),
                  t("ps4ota.update_online_pflicht", pflicht=t("ps4ota.ja") if info.pflicht else t("ps4ota.nein"))]
        for zeile in zeilen:
            self._protokoll(zeile)
        if info.version and not upd.ist_neuer(info.version, lokal):
            self._status(t("ps4ota.update_aktuell"))
            self._protokoll(t("ps4ota.update_aktuell"))
            return
        if info.verzeichnis is None or not info.verzeichnis.teile:
            self._warnung("ps4ota.update_ohne_teile")
            return
        if not messagebox.askyesno(t("ps4pkg.window_title"),
                                   t("ps4ota.update_laden_frage", version=info.version,
                                     groesse=self.g._fmt_bytes(info.groesse or info.verzeichnis.gesamtgroesse)),
                                   parent=self.win):
            return
        start = (spiel.basis.ordner if spiel and spiel.basis else "") or None
        ziel = filedialog.askdirectory(title=t("ps4ota.dlg_ziel_waehlen"), initialdir=start, parent=self.win)
        if not ziel:
            return
        ziel = os.path.normpath(ziel)
        self._update_nach = title_id
        self.warteschlange.hinzufuegen("update", t("ps4ota.aufg_titel_update", title_id=title_id, version=info.version),
                                       lambda a: au.arbeit_update_laden(a, info, ziel, t), quelle=title_id, ziel=ziel)
        self._knoepfe_pruefen()

    def _update_geladen(self, a: au.Aufgabe) -> None:
        """Das Update ist geladen (oder gescheitert): bei Erfolg als Paket in die Liste aufnehmen."""
        t = self.t
        if a.status == au.FERTIG and a.ergebnis and os.path.isfile(a.ergebnis):
            eintrag = bib.lese_paket(a.ergebnis)
            if all(os.path.normcase(e.pfad) != os.path.normcase(eintrag.pfad) for e in self.pakete):
                self.pakete.append(eintrag)
            self._protokoll(t("ps4dib.update_in_liste", pfad=a.ergebnis))
            self._gruppieren()
            self._balken_setzen(100.0)
            groesse = self.g._fmt_bytes(eintrag.groesse) if eintrag.groesse else "-"
            fertig = t("ps4dib.update_fertig", datei=os.path.basename(a.ergebnis), groesse=groesse)
            self._status(fertig)
            self._protokoll(fertig)
            self._liste_fuellen(auswaehlen=eintrag.title_id)
            messagebox.showinfo(t("ps4pkg.window_title"), fertig, parent=self.win)
        elif a.status == au.FEHLER:
            self._status(t("ps4ota.update_fehler", fehler=a.fehler))
            self._protokoll(a.fehler)
        else:
            self._status(t("ps4pkg.status_cancelled"))

    def _kurz_laeuft(self, a: au.Aufgabe) -> None:
        """Eine Aufgabe ausserhalb des Stapels (Update laden, senden, pruefen) zeigt ihren Stand."""
        self._balken_setzen(a.prozent)
        self._status("%s – %s" % (a.titel, a.text or "…"))
        gesehen = self._gelesen.get(a.kennung, 0)
        if len(a.protokoll) > gesehen:
            for zeile in a.protokoll[gesehen:]:
                self._protokoll(zeile)
            self._gelesen[a.kennung] = len(a.protokoll)

    def _kurz_beendet(self, a: au.Aufgabe) -> None:
        t = self.t
        gesehen = self._gelesen.get(a.kennung, 0)
        for zeile in a.protokoll[gesehen:]:
            self._protokoll(zeile)
        self._gelesen[a.kennung] = len(a.protokoll)
        if a.status == au.FERTIG:
            self._balken_setzen(100.0)
            self._status(a.text or t("ps4dib.fertig_kurz", titel=a.titel))
            self._protokoll(t("ps4dib.log_ok", titel=a.titel, pfad=a.ergebnis or a.ziel))
        elif a.status == au.ABGEBROCHEN:
            self._status(t("ps4pkg.status_cancelled"))
        else:
            self._status(t("ps4dib.log_fehler", titel=a.titel, grund=a.fehler))
            self._protokoll(t("ps4dib.log_fehler", titel=a.titel, grund=a.fehler))

    # ------------------------------------------------------------------
    # Senden (OTA)
    # ------------------------------------------------------------------
    def _senden(self) -> None:
        if not self._frei():
            return
        gewaehlt = self._gewaehlt()
        if not gewaehlt:
            self._warnung("ps4pkg.no_game")
            return
        if any(s.dump_ordner for s in gewaehlt):
            self._warnung("ps4dib.senden_nur_pakete")
            return
        if not self._basen_klaeren(gewaehlt):
            return
        pakete = [p for s in gewaehlt for p in s.pakete(mit_zusaetzen=True)]
        if not pakete:
            self._warnung("ps4dib.senden_nur_pakete")
            return
        t, c, F, pt = self.t, self.c, self.F, self.pt
        pw = self.g._pw
        dlg = self.g._build_modern_toplevel(t("ps4dib.btn_senden"), 640, 440, min_width=600, min_height=400)
        self.g._build_modern_header(dlg, t("ps4dib.btn_senden"), t("ps4dib.senden_untertitel"))
        rahmen = tk.Frame(dlg, bg=c["bg_main"], padx=20, pady=8)
        rahmen.pack(fill="both", expand=True)
        art_var = tk.StringVar(value=str(self._einstellung(EINST_OTA_ART, ART_DPI)))
        if art_var.get() not in (ART_DPI, ART_RPI):
            art_var.set(ART_DPI)
        ip = str(self._einstellung(EINST_IP, "") or "")
        if not ip:
            try:
                ip = self.g._ps5_ip("")
            except Exception:  # noqa: BLE001
                ip = ""
        ip_var = tk.StringVar(value=ip)
        port_var = tk.StringVar(value=str(self._einstellung(EINST_PORT, ota.STANDARD_PORT)))
        pc_var = tk.StringVar(value=t("ps4ota.ota_pc_auto"))
        serverport_var = tk.StringVar(value="0")
        erkannt_var = tk.StringVar(value="")
        gesamt = sum(p.groesse for p in pakete)
        tk.Label(rahmen, text=t("ps4dib.senden_kopf", anzahl=len(pakete), groesse=self.g._fmt_bytes(gesamt)),
                 font=(F, pt(10), "bold"), bg=c["bg_main"], fg=c["fg_primary"], anchor="w",
                 justify="left").pack(fill="x", pady=(0, 8))
        zeile_art = tk.Frame(rahmen, bg=c["bg_main"])
        zeile_art.pack(fill="x", pady=(0, 6))
        for wert, schluessel in ((ART_DPI, "ps4ota.ota_art_dpi"), (ART_RPI, "ps4ota.ota_art_rpi")):
            pw.Radiobutton(zeile_art, text=t(schluessel), value=wert, variable=art_var, font=(F, pt(9)),
                           bg=c["bg_main"], fg=c["fg_primary"], selectcolor=c["bg_card"],
                           activebackground=c["bg_main"], activeforeground=c["fg_primary"], highlightthickness=0,
                           bd=0).pack(side="left", padx=(0, 14))
        zeile_ip = tk.Frame(rahmen, bg=c["bg_main"])
        zeile_ip.pack(fill="x", pady=3)
        tk.Label(zeile_ip, text=t("ps4ota.ota_ip"), font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                 width=18, anchor="w").pack(side="left")
        pw.Entry(zeile_ip, textvariable=ip_var, width=18, font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_primary"],
                 insertbackground=c["fg_primary"], relief="flat").pack(side="left", ipady=3)
        tk.Label(zeile_ip, text=t("ps4ota.ota_port"), font=(F, pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"]).pack(side="left", padx=(14, 6))
        pw.Entry(zeile_ip, textvariable=port_var, width=7, font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_primary"],
                 insertbackground=c["fg_primary"], relief="flat").pack(side="left", ipady=3)
        zeile_pc = tk.Frame(rahmen, bg=c["bg_main"])
        tk.Label(zeile_pc, text=t("ps4ota.ota_pc"), font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                 width=18, anchor="w").pack(side="left")
        pc_box = pw.Combobox(zeile_pc, textvariable=pc_var, width=22, font=(F, pt(9)),
                             values=tuple([t("ps4ota.ota_pc_auto")] + ota.lokale_adressen()))
        pc_box.pack(side="left")
        tk.Label(zeile_pc, text=t("ps4ota.ota_serverport"), font=(F, pt(9)), bg=c["bg_main"],
                 fg=c["fg_secondary"]).pack(side="left", padx=(14, 6))
        pw.Entry(zeile_pc, textvariable=serverport_var, width=7, font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_primary"],
                 insertbackground=c["fg_primary"], relief="flat").pack(side="left", ipady=3)
        erkannt_zeile = tk.Label(rahmen, textvariable=erkannt_var, font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_success"],
                                 anchor="w")
        erkannt_zeile.pack(fill="x", pady=(4, 0))
        hinweis = tk.Label(rahmen, text="", font=(F, pt(8)), bg=c["bg_main"], fg=c["fg_secondary"], anchor="w",
                           justify="left", wraplength=520)
        hinweis.pack(fill="x", pady=(2, 8))

        def art_geaendert(*_a) -> None:
            if art_var.get() == ART_RPI:
                zeile_pc.pack(fill="x", pady=3, before=erkannt_zeile)
                hinweis.configure(text=t("ps4ota.ota_hinweis_rpi"))
            else:
                zeile_pc.pack_forget()
                hinweis.configure(text=t("ps4ota.ota_hinweis_dpi"))

        def ziel() -> "tuple[str, int] | None":
            adresse = ip_var.get().strip()
            if not ota.adresse_gueltig(adresse):
                messagebox.showwarning(t("ps4pkg.window_title"), t("ps4ota.ota_ip_ungueltig"), parent=dlg)
                return None
            try:
                port = int(port_var.get().strip())
                if not 1 <= port <= 65535:
                    raise ValueError(port)
            except ValueError:
                messagebox.showwarning(t("ps4pkg.window_title"), t("ps4ota.ota_port_ungueltig"), parent=dlg)
                return None
            self._merken(EINST_IP, adresse)
            self._merken(EINST_PORT, port)
            self._merken(EINST_OTA_ART, art_var.get())
            return adresse, port

        def erkennen() -> None:
            z = ziel()
            if z is None:
                return
            erkannt_var.set(t("ps4ota.ota_erkenne"))
            self._z["ota_erkannt"] = None
            self._z["ota_dialog"] = (art_var, erkannt_var, art_geaendert, dlg)

            def arbeit() -> None:
                self._z["ota_erkannt"] = ota.erkennen(z[0], z[1])

            threading.Thread(target=arbeit, daemon=True, name="ps4dib-erkennen").start()

        def senden() -> None:
            z = ziel()
            if z is None:
                return
            adresse, port = z
            art = art_var.get()
            if not messagebox.askyesno(
                    t("ps4pkg.window_title"),
                    t("ps4ota.ota_frage", anzahl=len(pakete), groesse=self.g._fmt_bytes(gesamt), ip=adresse,
                      art=t("ps4ota.ota_art_dpi") if art == ART_DPI else t("ps4ota.ota_art_rpi")), parent=dlg):
                return
            self._batch, self._gemeldet, self._gelesen = [], set(), {}
            if art == ART_DPI:
                for p in pakete:
                    self.warteschlange.hinzufuegen(
                        "ota", t("ps4ota.aufg_titel_ota", datei=p.datei, ip=adresse),
                        lambda a, pfad=p.pfad: au.arbeit_ota_dpi(a, pfad, adresse, port, t), quelle=p.pfad, ziel=adresse)
            else:
                pc = pc_var.get().strip()
                eigene = "" if (not pc or pc == t("ps4ota.ota_pc_auto")) else pc
                try:
                    server_port = max(0, int(serverport_var.get().strip() or "0"))
                except ValueError:
                    server_port = 0
                pfade = [p.pfad for p in pakete]
                self.warteschlange.hinzufuegen(
                    "ota", t("ps4ota.aufg_titel_ota_rpi", anzahl=len(pfade), ip=adresse),
                    lambda a: au.arbeit_ota_rpi(a, pfade, adresse, port, t, eigene_ip=eigene, server_port=server_port),
                    quelle=pfade[0], ziel=adresse)
            self._protokoll(t("ps4dib.senden_gestartet", anzahl=len(pakete), ip=adresse))
            dlg.destroy()
            self._knoepfe_pruefen()

        knoepfe = tk.Frame(rahmen, bg=c["bg_main"])
        knoepfe.pack(fill="x", pady=(6, 0))
        pw.Button(knoepfe, text=t("ps4ota.ota_senden"), style="Accent.TButton", command=senden).pack(side="left")
        pw.Button(knoepfe, text=t("ps4ota.ota_erkennen"), command=erkennen).pack(side="left", padx=(8, 0))
        pw.Button(knoepfe, text=t("action.cancel"), command=dlg.destroy).pack(side="right")
        raster.spur_bis_zerstoert(dlg, art_var, art_geaendert)
        art_geaendert()

    def _ota_ergebnis(self) -> None:
        roh = self._z.get("ota_erkannt")
        dialog = self._z.get("ota_dialog")
        if roh is None or not dialog:
            return
        self._z["ota_erkannt"] = None
        art_var, erkannt_var, art_geaendert, dlg = dialog
        try:
            if not dlg.winfo_exists():
                return
        except tk.TclError:
            return
        t = self.t
        if roh == ota.ART_DPI_API:
            art_var.set(ART_DPI)
            erkannt_var.set(t("ps4ota.ota_erkannt_dpi"))
        elif roh == ota.ART_DPI_WEB:
            art_var.set(ART_DPI)
            erkannt_var.set(t("ps4ota.ota_erkannt_dpi_web"))
        elif roh == ota.ART_RPI:
            art_var.set(ART_RPI)
            erkannt_var.set(t("ps4ota.ota_erkannt_rpi"))
        else:
            erkannt_var.set(t("ps4ota.ota_nichts"))
        art_geaendert()

    # ------------------------------------------------------------------
    # Mehr
    # ------------------------------------------------------------------
    def _mehr_menue(self) -> None:
        t = self.t
        menue = self._menue()
        mehrere = any(len(s.basen) > 1 for s in self._gewaehlt())
        menue.add_command(label=t("ps4dib.mehr_basis"), command=self._basis_menue,
                          state="normal" if mehrere else "disabled")
        menue.add_command(label=t("ps4dib.mehr_pruefen"), command=self._pakete_pruefen)
        menue.add_command(label=t("ps4dib.mehr_kopf"), command=self._paketkopf)
        if not orbispkg.verfuegbar():
            menue.add_command(label=t("ps4dib.mehr_entpacker"), command=self._alter_entpacker)
        try:
            menue.tk_popup(self.mehr_knopf.winfo_rootx(), self.mehr_knopf.winfo_rooty() + self.mehr_knopf.winfo_height())
        finally:
            menue.grab_release()

    def _pakete_pruefen(self) -> None:
        if not self._frei():
            return
        gewaehlt = self._gewaehlt()
        if not gewaehlt:
            self._warnung("ps4pkg.no_game")
            return
        if not orbispkg.verfuegbar():
            self._warnung("ps4dib.ohne_orbis", system=sys.platform)
            return
        t = self.t
        self._batch, self._gemeldet, self._gelesen = [], set(), {}
        for s in gewaehlt:
            for p in s.pakete(mit_zusaetzen=True):
                self.warteschlange.hinzufuegen("pruefen", t("ps4ota.aufg_titel_pruefen", datei=p.datei),
                                               lambda a, pfad=p.pfad: au.arbeit_pruefen(a, pfad, t), quelle=p.pfad)
        self._knoepfe_pruefen()

    def _paketkopf(self) -> None:
        oeffnen = getattr(self.g, "_show_pkg_reader", None)
        if callable(oeffnen):
            oeffnen()

    def _alter_entpacker(self) -> None:
        oeffnen = getattr(self.g, "_show_pkg_entpacken", None)
        if callable(oeffnen):
            oeffnen()


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int], vorgabe: str = "") -> Ps4DumpImageFenster:
    """Oeffnet das Fenster - oder holt das offene nach vorn (dann mit der neuen Vorgabe, falls es eine gibt)."""
    vorhanden = getattr(gui, FENSTER_ATTRIBUT, None)
    if vorhanden is not None:
        try:
            if vorhanden.win.winfo_exists():
                vorhanden.win.deiconify()
                vorhanden.win.lift()
                if vorgabe:
                    vorhanden.art_var.set(QUELLE_DATEIEN)
                    vorhanden.quelle_var.set(vorgabe)
                    vorhanden._einlesen()
                return vorhanden
        except tk.TclError:
            pass
    fenster = Ps4DumpImageFenster(gui, schrift, mono, pt, vorgabe)
    setattr(gui, FENSTER_ATTRIBUT, fenster)
    return fenster
