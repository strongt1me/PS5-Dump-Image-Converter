# -*- coding: utf-8 -*-
"""Die Seite „FPKG“ unter Aufgabe 7 „PKG / FPKG“ (seit v1.9.71 bis 12.10.2026 abends ein eigenes Fenster unter
WEITERE TOOLS: „PS5 PKG Dump & Image Converter“).

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

Seit dem 12.10.2026 (Nutzerwunsch) baut :meth:`Ps5PkgFenster._bauen` ``self.win`` als ``tk.Frame`` statt als
eigenes Popup-Fenster - eingebettet in die Seite ``ui/pkg_fpkg_seite.py`` (Knopf "FPKG"). Name, Attribut
(``FENSTER_ATTRIBUT``) und ``oeffnen()`` blieben bewusst stehen (siehe ``ui/ps4_dump_image.py`` fuer die
ausfuehrlichere Begruendung) - nur ohne SCHLIESSEN mehr: die Seite bleibt wie die anderen Seiten stehen.
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
from tkinter import filedialog, messagebox
from typing import Callable

from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import konsole_ftp as ftp
from ps5_validator.utils import pkg_direkt
from ps5_validator.utils import ps5_pkg_optionen as opt
from ps5_validator.utils import ps5_pkg_werkzeug as wz
from ps5_validator.utils import prospero_pkg_tool as ppt
from ps5_validator.ui import ps5_pkg_optionen as optionen_ui
from ps5_validator.ui import pkg_datei_browser as browser_ui
from ps5_validator.ui import spiel_detail_fenster as detail_ui

logger = logging.getLogger("PS5Converter.ui.ps5_pkg_fenster")

FENSTER_ATTRIBUT = "_ps5_pkg_fenster"
TAKT_MS = 250

EINST_ZIEL = "ps5pkg_ziel"
EINST_FORMAT = "ps5pkg_format"
EINST_BIBLIOTHEK = "ps5pkg_bibliothek"
EINST_AKTION = "ps5pkg_aktion"
EINST_FERN = "ps5pkg_fern"

AKTION_UMWANDELN = "umwandeln"
AKTION_EXTRAHIEREN = "extrahieren"
AKTION_PRUEFEN = "pruefen"
#: Das Paket gleich auf die PS5 entpacken, ohne Kopie auf dem PC (:mod:`pkg_direkt`, seit v1.9.72).
AKTION_KONSOLE = "konsole"
AKTIONEN = (AKTION_UMWANDELN, AKTION_EXTRAHIEREN, AKTION_PRUEFEN, AKTION_KONSOLE)

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
_FW = re.compile(r"^(?:fw|firmware):(<=|>=|<|>)?(\d+(?:[.,]\d+)?)$", re.IGNORECASE)
_SDK = re.compile(r"^sdk:(<=|>=|<|>)?(\d+(?:[.,]\d+)?)$", re.IGNORECASE)


def _fw_als_zahl(text: str) -> float:
    """'9.00' -> 9.0, '11.50' -> 11.5 fuer numerischen Vergleich."""
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return 0.0


def _param_fw_zahl(info: "wz.PaketInfo", schluessel: str) -> float:
    p = info.param if isinstance(info.param, dict) else {}
    return _fw_als_zahl(firmware_text(p.get(schluessel, "")))


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
    treffer = _FW.match(wort)
    if treffer:
        vergleich, grenze = treffer.group(1) or ">=", _fw_als_zahl(treffer.group(2))
        wert = _param_fw_zahl(info, "requiredSystemSoftwareVersion")
        return {"<": wert < grenze, "<=": wert <= grenze, ">": wert > grenze, ">=": wert >= grenze}[vergleich]
    treffer = _SDK.match(wort)
    if treffer:
        vergleich, grenze = treffer.group(1) or ">=", _fw_als_zahl(treffer.group(2))
        wert = _param_fw_zahl(info, "sdkVersion")
        return {"<": wert < grenze, "<=": wert <= grenze, ">": wert > grenze, ">=": wert >= grenze}[vergleich]
    heu = " ".join([info.titel, info.title_id, info.content_id, os.path.basename(info.pfad)]).lower()
    return klein in heu


def _gruppe_passt(info: "wz.PaketInfo", gruppe: str) -> bool:
    """Alle Woerter einer UND-Gruppe muessen passen; leere Gruppe passt immer."""
    for wort in gruppe.split():
        ausschluss = wort.startswith("-") and len(wort) > 1
        passt = _wort_passt(info, wort[1:] if ausschluss else wort)
        if passt == ausschluss:
            return False
    return True


def suche_passt(info: "wz.PaketInfo", suche: str) -> bool:
    """Passt das Paket zur Suche? ``|`` trennt ODER-Gruppen (mindestens eine muss passen);
    innerhalb einer Gruppe: UND; ``-wort`` schliesst aus; ``titel:``, ``id:``, ``fw:>9.00``,
    ``sdk:>=5``, ``groesse:>50GB`` (auch ``<``, ``>=``, ``<=``) schraenken ein."""
    gruppen = suche.split("|")
    for gruppe in gruppen:
        if _gruppe_passt(info, gruppe.strip()):
            return True
    return False


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
    """Die Seite. Eine Instanz je Programmlauf (Singleton, siehe :func:`oeffnen`)."""

    def __init__(self, gui, schrift: str, mono: str, pt: Callable[[int], int], vorgabe: str = "",
                 *, master: "tk.Misc | None" = None) -> None:
        self.g = gui
        self.t = gui._t
        self.c = gui._COLORS
        self.F = schrift
        self.M = mono
        self.pt = pt
        self._master = master
        self.pakete: list[wz.PaketInfo] = []
        self.aktuell: "wz.PaketInfo | None" = None
        self.format_schluessel = "ffpfsc"
        self._sperre = threading.Lock()
        self._z: dict = {"zeilen": [], "prozent": None, "schritt_text": None, "schritt": None, "fertig": None,
                         "gelesen": [], "lesen_laeuft": 0, "scan": []}
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
        self._werkzeug_ppt_pfad = ""
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

    def _werkzeug_ppt(self) -> str:
        """Pfad zu ProsperoPkgTool - dem zweiten, waehlbaren Paketersteller (nur fuer "Paket bauen")."""
        if not self._werkzeug_ppt_pfad or not os.path.isfile(self._werkzeug_ppt_pfad):
            self._werkzeug_ppt_pfad = ppt.werkzeug_suchen(self._wurzeln())
        return self._werkzeug_ppt_pfad

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
        """Aus jedem Faden: eine Zeile fuers Protokoll - die Ausgaben des Werkzeugs in Worten (:meth:`_lesbar`)."""
        text = self._lesbar(text)
        if not text:
            return
        with self._sperre:
            self._z["zeilen"].append(text)

    #: Ausgaben des Werkzeugs, die im Protokoll in Worten stehen - (Muster, Textschluessel). Der Rest bleibt, ohne
    #: die Kennung "[info]" davor. Nutzer 14.10.2026: "im Status-Log verstehe ich nur Bahnhof".
    _LESBAR = (
        (re.compile(r"^\[info\] Paketinhalt wird gelesen"), "ps5pkg.log_reading_contents"),
        (re.compile(r"^\[info\] Paketinhalt gelesen: (?P<anzahl>\d+) Eintraege in (?P<sekunden>\d+) s"),
         "ps5pkg.log_contents_read"),
        (re.compile(r"^\[info\] extract-inner \(members\).*\((?P<anzahl>\d+) member\(s\)\)\s*$"),
         "ps5pkg.log_extracting_files"),
        (re.compile(r"^\[info\] extract-inner\b"), "ps5pkg.log_extracting_all"),
        (re.compile(r"^OK\W+extracted (?P<anzahl>\d+) file"), "ps5pkg.log_extracted"),
        (re.compile(r"^\[info\] (kein Fortschritt je Datei|Entpacken je Datei gescheitert)"), "ps5pkg.log_whole_extract"),
    )

    def _lesbar(self, text: str) -> str:
        text = str(text or "").strip()
        for muster, schluessel in self._LESBAR:
            treffer = muster.search(text)
            if treffer:
                return self.t(schluessel, **treffer.groupdict())
        if text.startswith("[info] "):
            return text[len("[info] "):]
        return text

    def _status(self, text: str) -> None:
        try:
            self.status_var.set(text)
        except tk.TclError:
            pass

    def _arbeitsordner(self) -> str:
        """Ordner fuer Staging (Entpacken/Bauen/Extrahieren).

        Seit v1.9.83 geht ein eigener, in den Optionen gesetzter Temp-Ordner (``opt.TEMP_ORDNER``) vor - nur
        wenn er wirklich da ist, sonst wie bisher der Temp-Ordner aus den Haupteinstellungen bzw. System-Temp.
        Leer (Vorgabe) aendert nichts am bisherigen Verhalten.
        """
        eigener = str(self._einstellung(opt.TEMP_ORDNER, "")).strip()
        if eigener and os.path.isdir(eigener):
            return eigener
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
        self.win = tk.Frame(self._master if self._master is not None else g.root, bg=c["bg_main"])
        if self._master is None:
            # Ohne eine Seite, die sie eingebettet reicht (z. B. direkt im Test erzeugt): eine feste Groesse wie
            # das fruehere Popup-Fenster (1240x840), sonst bleibt der Rahmen 1x1 px - Kinder, die auf ein echtes
            # Groessenereignis warten (etwa die FlussZeile der Aktions-Kacheln), bekommen dann nie eines.
            self.win.place(x=0, y=0, width=1240, height=840)
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
        # Auf die PS5 entpacken: die Adresse ist die der Ansicht KONSOLE (ein Feld fuer alle Seiten), der Ordner gemerkt.
        self.adresse_var = g._konsole_ip_var()
        self.fern_var = tk.StringVar(value=str(self._einstellung(EINST_FERN, "/mnt/usb0") or "/mnt/usb0"))
        self._konsole_ansicht = False
        self._konsole_ziel = ("", "")              # (Adresse, Ordner) fuer den Arbeitsfaden - er liest keine Tk-Variable
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
        rumpf = tk.Frame(self.win, bg=c["bg_main"])
        rumpf.pack(fill="both", expand=True)
        rumpf.columnconfigure(1, weight=1)
        rumpf.rowconfigure(0, weight=1)
        self._navigation(rumpf)
        flaeche = tk.Frame(rumpf, bg=c["bg_main"])
        flaeche.grid(row=0, column=1, sticky="nsew", padx=(0, 14))
        flaeche.columnconfigure(0, weight=1)
        flaeche.rowconfigure(0, weight=1)
        # Die Knopfleiste liegt in derselben Spalte wie die Karten (Zeile darunter, ohne Gewicht - sie behaelt ihre
        # Hoehe, wenn der Platz knapp wird): so stehen "Umwandlung starten" und "Abbrechen" buendig mit der linken Kante
        # der Karten. Bis 12.10.2026 hing sie ueber die ganze Breite unten und ragte links ueber die Navigation hinaus.
        leiste = tk.Frame(rumpf, bg=c["bg_main"], pady=8)
        leiste.grid(row=1, column=1, sticky="ew", padx=(0, 14))
        self.start_knopf = self._pille(leiste, "ps5pkg.start_button", self._starten, akzent=True)
        self.start_knopf.pack(side="left")
        self.abbrechen_knopf = self._pille(leiste, "action.cancel", self._abbrechen)
        self.abbrechen_knopf.pack(side="left", padx=(10, 0))
        self.abbrechen_knopf.configure(state="disabled")
        self.browser_knopf = self._pille(leiste, "ps5pkg.browser_button", self._browser_oeffnen)
        self.browser_knopf.pack(side="left", padx=(24, 0))
        self.detail_knopf = self._pille(leiste, "ps5pkg.detail_button", self._detail_oeffnen)
        self.detail_knopf.pack(side="left", padx=(10, 0))
        self.seiten = {"umwandeln": tk.Frame(flaeche, bg=c["bg_main"]),
                       "bibliothek": tk.Frame(flaeche, bg=c["bg_main"]),
                       "extras": tk.Frame(flaeche, bg=c["bg_main"])}
        for seite in self.seiten.values():
            seite.grid(row=0, column=0, sticky="nsew")
        self._seite_umwandeln(self.seiten["umwandeln"])
        self._seite_bibliothek(self.seiten["bibliothek"])
        self._seite_extras(self.seiten["extras"])
        self._seite_zeigen("umwandeln")

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
        for schluessel, zeichen, text in (("umwandeln", "⇄", "ps5pkg.nav_convert"), ("bibliothek", "▥", "ps5pkg.nav_library"),
                                          ("extras", "⚒", "ps5pkg.nav_extras"), ("optionen", "⚙", "ps5pkg.nav_options")):
            rahmen = tk.Frame(leiste, bg=c["bg_main"], cursor="hand2", pady=8)
            rahmen.pack(fill="x", pady=(0, 6))
            symbol = tk.Label(rahmen, text=zeichen, font=(F, pt(18)), bg=c["bg_main"], fg=c["fg_secondary"])
            symbol.pack()
            name = tk.Label(rahmen, text=self.t(text), font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"])
            name.pack()
            # "Optionen" ist keine Seite, sondern ein Dialog: Der Eintrag bleibt nie als gewaehlte Seite stehen.
            befehl = self._optionen_oeffnen if schluessel == "optionen" else (lambda s=schluessel: self._seite_zeigen(s))
            for w in (rahmen, symbol, name):
                w.bind("<Button-1>", lambda _e, b=befehl: b())
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
        seite.rowconfigure(0, weight=1)

        # Seit dem 12.10.2026 (Nutzerwunsch) kein eigener Seitentitel mehr: Die Seite liegt eingebettet unter
        # "7. PKG / FPKG" (Knopf "FPKG"), die schon eine Ueberschrift traegt - und der Platz fehlte sonst der
        # Karte AUFTRAG (Schrittfortschritt/Auftragsschritte waren bei kleiner Fensterhoehe kaum noch zu sehen).
        # QUELLE+ZIELFORMAT+AUFTRAG stapeln sich hier; bei knapper Fensterhoehe reichten
        # sie ueber den sichtbaren Bereich hinaus, ohne jede Moeglichkeit zu rollen
        # (derselbe Fund wie bei den Seiten Extras und Bibliothek, 18.10.2026: gemessen
        # 901 px Inhalt gegen 750 px sichtbar). Nur diese Spalte wird eingepackt - die
        # rechte Spalte bleibt direkt in "seite", damit sie weiter ueber die Zeilenhoehe
        # von "seite" mitwaechst statt auf ihre eigene Inhaltsgroesse zu schrumpfen.
        links_aussen, links = g._build_scrollable_body(seite)
        links_aussen.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        links.columnconfigure(0, weight=1)
        rechts = tk.Frame(seite, bg=c["bg_main"], width=380)
        rechts.grid(row=0, column=1, sticky="ns")
        # Die Kinder werden gepackt, nicht gegridet: Erst pack_propagate(False) haelt die Breite von 380 fest (bis
        # 13.10.2026 stand hier grid_propagate - ohne Wirkung; die Spalte war so breit wie ihr Inhalt und sprang, sobald
        # ein Cover erschien).
        rechts.pack_propagate(False)
        self.spalte_rechts = rechts

        # QUELLE
        quelle = self._karte(links, "ps5pkg.card_source")
        self.quelle_karte = quelle          # daran richtet die Seite PKG/FPKG ihren Knopf "PKG" aus
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

        # Das gewaehlte Paket steht fuer sich: Trennlinie, kleine Ueberschrift, Titel, Pfad - und erst darunter, wieder
        # durch eine Linie getrennt, die Aktionen (Nutzer 11.10.2026: "viel zu nah beim Erstellen-Knopf, unuebersichtlich").
        tk.Frame(quelle, height=1, bg=c["border"]).pack(fill="x", pady=(14, 0))
        self.paket_kopf = tk.Label(quelle, text=t("ps5pkg.selected_caption"), font=(F, pt(8), "bold"),
                                   bg=c["bg_card"], fg=c["fg_secondary"], anchor="w")
        self.paket_kopf.pack(fill="x", pady=(10, 0))
        self.paket_titel = tk.Label(quelle, text=t("ps5pkg.no_source"), font=(F, pt(13), "bold"),
                                    bg=c["bg_card"], fg=c["fg_primary"], anchor="w")
        self.paket_titel.pack(fill="x", pady=(2, 0))
        zeile = tk.Frame(quelle, bg=c["bg_card"])
        zeile.pack(fill="x", pady=(2, 0))
        self.paket_pfad = tk.Label(zeile, text="", font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"], anchor="w")
        self.paket_pfad.pack(side="left", fill="x", expand=True)
        self.paket_typ = tk.Label(zeile, text="", font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_accent"], padx=10)
        self.paket_typ.pack(side="right")
        self.paket_playgo = tk.Label(quelle, text="", font=(F, pt(9), "bold"), bg=c["bg_card"],
                                     fg=c.get("fg_warning", "#f0a32e"), anchor="w")
        self.paket_playgo.pack(fill="x")
        tk.Frame(quelle, height=1, bg=c["border"]).pack(fill="x", pady=(14, 0))
        # Vier Aktionen passen bei der Mindestbreite nicht mehr in eine Zeile: Die Zeile bricht um, statt abzuschneiden.
        aktion = raster.FlussZeile(quelle, g._bibliothek_zeichner(), grund="bg_card", abstand=(14, 4))
        aktion.pack(fill="x", pady=(12, 0))
        self.aktion_reihe = aktion
        beschriftung = tk.Label(aktion, text=t("ps5pkg.action_label"), font=(F, pt(10)), bg=c["bg_card"],
                                fg=c["fg_secondary"])
        aktion.hinzufuegen(beschriftung)
        self._aktion_knoepfe = {}
        for wert, schluessel in ((AKTION_UMWANDELN, "ps5pkg.action_convert"), (AKTION_EXTRAHIEREN, "ps5pkg.action_extract"),
                                 (AKTION_PRUEFEN, "ps5pkg.action_check"), (AKTION_KONSOLE, "ps5pkg.action_console")):
            knopf = pw.Radiobutton(aktion, text=t(schluessel), value=wert, variable=self.aktion_var, font=(F, pt(10)),
                                   command=self._aktion_geaendert, bg=c["bg_card"], fg=c["fg_primary"],
                                   selectcolor=c["bg_card"], activebackground=c["bg_card"],
                                   activeforeground=c["fg_primary"], highlightthickness=0, bd=0)
            aktion.hinzufuegen(knopf)
            self._aktion_knoepfe[wert] = knopf
        ziel = tk.Frame(quelle, bg=c["bg_card"])
        ziel.pack(fill="x", pady=(10, 0))
        self.ziel_reihe = ziel
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
        # Auf die PS5 entpacken: statt des Zielordners auf dem PC die Adresse und der Ordner auf der Konsole. Erst
        # sichtbar, wenn diese Aktion gewaehlt ist (:meth:`_aktion_anwenden`).
        fern = tk.Frame(quelle, bg=c["bg_card"])
        self.fern_reihe = fern
        fern.columnconfigure(1, weight=1)
        optionen = dict(font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_primary"], insertbackground=c["fg_primary"],
                        relief="flat")
        tk.Label(fern, text=t("ps5pkg.console_address"), font=(F, pt(10)), bg=c["bg_card"], fg=c["fg_secondary"]).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.adresse_feld = pw.Entry(fern, textvariable=self.adresse_var, **optionen)
        self.adresse_feld.grid(row=0, column=1, sticky="ew", ipady=3)
        tk.Label(fern, text=t("ps5pkg.console_folder"), font=(F, pt(10)), bg=c["bg_card"], fg=c["fg_secondary"]).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(6, 0))
        self.fern_feld = pw.Entry(fern, textvariable=self.fern_var, **optionen)
        self.fern_feld.grid(row=1, column=1, sticky="ew", ipady=3, pady=(6, 0))
        self.fern_feld.bind("<KeyRelease>", lambda _e: self._ergebnis_fuellen(), add="+")
        hinweis = tk.Label(fern, text=t("ps5pkg.console_hint"), font=(F, pt(9)), bg=c["bg_card"], fg=c["fg_secondary"],
                           anchor="w", justify="left", wraplength=520)
        hinweis.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        hinweis.bind("<Configure>", lambda e: hinweis.configure(wraplength=max(120, e.width - 6)))

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
        textknoepfe = tk.Frame(auftrag, bg=c["bg_card"])
        textknoepfe.pack(fill="x", pady=(10, 0))
        self.ausgabe_knopf = self._pille(textknoepfe, "ps5pkg.open_output", self._ausgabe_oeffnen, klein=True)
        self.ausgabe_knopf.pack(side="left")
        self._pille(textknoepfe, "ps5pkg.clear_log", self._verlauf_leeren, klein=True).pack(side="left", padx=(8, 0))
        # Was gerade entsteht (Datei, Menge, Dateien, Zeit) - unter den Knoepfen, buendig mit "Ausgabe oeffnen", ueber die
        # ganze Breite der Karte (Nutzer 14.10.2026: neben "Verlauf leeren" war zu wenig Platz, die Zeile lief ab).
        self.datei_var = tk.StringVar(value="")
        datei_zeile = tk.Label(auftrag, textvariable=self.datei_var, font=(F, pt(9)), bg=c["bg_card"],
                               fg=c["fg_secondary"], anchor="w", justify="left")
        # expand: steht mittig im freien Raum zwischen den Knoepfen und der Unterkante der Karte (Nutzer 14.10.2026)
        datei_zeile.pack(fill="x", expand=True, pady=(8, 0))
        datei_zeile.bind("<Configure>", lambda e: datei_zeile.configure(wraplength=max(120, e.width - 4)))

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
        self.ergebnis_karte = ergebnis
        # Das Cover steht seit dem 13.10.2026 (Nutzerwunsch) nicht mehr hier, sondern wie bei den Aufgaben 1 bis 6 in der
        # Seitenleiste (:meth:`_spielinfo_zeigen`); der Knopf "Vorschau oeffnen" ist entfallen.
        # Das Protokoll liegt unter dem Ergebnis: In der Karte AUFTRAG blieb ihm bei normaler Fensterhoehe keine Hoehe -
        # der Text war nicht zu sehen. Es fuellt den Rest der Spalte; die Breite bestimmt die Spalte (width=1), nicht
        # der Text.
        self.protokoll = pw.Text(rechts, height=6, width=1, font=(self.M, pt(9)), bg=c["console_bg"],
                                 fg=c["console_fg"], relief="flat", wrap="word", state="disabled")
        self.protokoll.pack(fill="both", expand=True, pady=(12, 0))
        # Abstand nach jeder Meldung (nicht zwischen den umbrochenen Zeilen einer Meldung) - so steht jede fuer sich und
        # liest sich leichter (Nutzer 14.10.2026).
        try:
            self.protokoll.configure(spacing3=max(20, int(pt(22))))
        except tk.TclError:
            pass

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
        # Die Karten COVER+TECH liefen bei knapper Fensterhoehe ueber den sichtbaren
        # Bereich hinaus, ohne jede Moeglichkeit zu rollen (derselbe Fund wie bei der
        # Seite Extras, 18.10.2026: gemessen 835 px Inhalt gegen 750 px sichtbar).
        rechts_rahmen = tk.Frame(seite, bg=c["bg_main"], width=420)
        rechts_rahmen.grid(row=1, column=1, sticky="ns")
        rechts_rahmen.grid_propagate(False)
        rechts_aussen, rechts = g._build_scrollable_body(rechts_rahmen)
        rechts_aussen.pack(fill="both", expand=True)

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

    # ---------------- Seite Extras (SDK-Werkzeuge) ----------------
    def _seite_extras(self, seite) -> None:
        g, t, c = self.g, self.t, self.c
        F, pt = self.F, self.pt
        pw = g._pw
        seite.columnconfigure(0, weight=1)
        seite.rowconfigure(1, weight=1)
        kopf = tk.Frame(seite, bg=c["bg_main"])
        kopf.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        tk.Label(kopf, text=t("ps5pkg.nav_extras"), font=(F, pt(20), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(fill="x")

        # Vier Karten stapeln sich hier - bei kleineren Fenstern reichten sie
        # ueber den sichtbaren Bereich hinaus, ohne jede Moeglichkeit zu
        # rollen: der Entpacken-Knopf, der ganze Aufbauen-Bereich der dritten
        # Karte und die vierte Karte waren schlicht nicht erreichbar.
        aussen, innen = g._build_scrollable_body(seite)
        aussen.grid(row=1, column=0, sticky="nsew")
        innen.columnconfigure(0, weight=1)

        karte = self._karte(innen, "ps5pkg.dds_title")
        karte.grid(row=0, column=0, sticky="ew")

        # Innerer Frame fuer grid (Karte-Titel wurde per pack gesetzt; grid-Kinder muessen in einem eigenen Frame)
        inhalt = tk.Frame(karte, bg=c["bg_card"])
        inhalt.pack(fill="both", expand=True)
        inhalt.columnconfigure(1, weight=1)

        tk.Label(inhalt, text=t("ps5pkg.dds_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], wraplength=540, justify="left", anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        tk.Label(inhalt, text=t("ps5pkg.dds_lbl_source"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._dds_quelle_var = tk.StringVar()
        pw.Entry(inhalt, textvariable=self._dds_quelle_var, font=(F, pt(10))).grid(
            row=1, column=1, sticky="ew", padx=(0, 8))
        self._pille(inhalt, "ps5pkg.dds_btn_source", self._dds_quelle_waehlen, klein=True).grid(row=1, column=2)

        tk.Label(inhalt, text=t("ps5pkg.dds_lbl_target"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._dds_ziel_var = tk.StringVar()
        pw.Entry(inhalt, textvariable=self._dds_ziel_var, font=(F, pt(10))).grid(
            row=2, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        self._pille(inhalt, "ps5pkg.dds_btn_target", self._dds_ziel_waehlen, klein=True).grid(row=2, column=2, pady=(8, 0))

        self._dds_alpha_var = tk.BooleanVar()
        pw.Checkbutton(inhalt, text=t("ps5pkg.dds_chk_alpha"), variable=self._dds_alpha_var,
                       font=(F, pt(10))).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._dds_status = tk.Label(inhalt, text="", font=(F, pt(9)), bg=c["bg_card"],
                                    fg=c["fg_secondary"], anchor="w", wraplength=540)
        self._dds_status.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        self._pille(inhalt, "ps5pkg.dds_btn_run", self._dds_konvertieren, akzent=True).grid(
            row=5, column=0, columnspan=3, pady=(12, 0), sticky="w")

        # ---- exFAT Boot-Sektor reparieren (Nr. 3) ----
        karte_rep = self._karte(innen, "ps5pkg.exfat_repair_title")
        karte_rep.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        ir = tk.Frame(karte_rep, bg=c["bg_card"])
        ir.pack(fill="both", expand=True)
        ir.columnconfigure(1, weight=1)
        tk.Label(ir, text=t("ps5pkg.exfat_repair_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], wraplength=540, justify="left", anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        tk.Label(ir, text=t("ps5pkg.exfat_repair_lbl_file"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._exfat_rep_pfad_var = tk.StringVar()
        pw.Entry(ir, textvariable=self._exfat_rep_pfad_var, font=(F, pt(10))).grid(
            row=1, column=1, sticky="ew", padx=(0, 8))
        self._pille(ir, "ps5pkg.exfat_repair_btn_file", self._exfat_rep_waehlen, klein=True).grid(row=1, column=2)
        self._exfat_rep_status = tk.Label(ir, text="", font=(F, pt(9)), bg=c["bg_card"],
                                          fg=c["fg_secondary"], anchor="w", wraplength=540)
        self._exfat_rep_status.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._pille(ir, "ps5pkg.exfat_repair_btn_run", self._exfat_reparieren, akzent=True).grid(
            row=3, column=0, columnspan=3, pady=(12, 0), sticky="w")

        # ---- exFAT-Inhalt bearbeiten (Nr. 2) ----
        karte_edit = self._karte(innen, "ps5pkg.exfat_edit_title")
        karte_edit.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ie = tk.Frame(karte_edit, bg=c["bg_card"])
        ie.pack(fill="both", expand=True)
        ie.columnconfigure(1, weight=1)
        tk.Label(ie, text=t("ps5pkg.exfat_edit_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], wraplength=540, justify="left", anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        # Entpacken-Bereich
        tk.Label(ie, text=t("ps5pkg.exfat_edit_lbl_source"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._exfat_edit_quelle_var = tk.StringVar()
        pw.Entry(ie, textvariable=self._exfat_edit_quelle_var, font=(F, pt(10))).grid(
            row=1, column=1, sticky="ew", padx=(0, 8))
        self._pille(ie, "ps5pkg.exfat_edit_btn_source", self._exfat_edit_quelle_waehlen, klein=True).grid(row=1, column=2)
        tk.Label(ie, text=t("ps5pkg.exfat_edit_lbl_folder"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._exfat_edit_ordner_var = tk.StringVar()
        pw.Entry(ie, textvariable=self._exfat_edit_ordner_var, font=(F, pt(10))).grid(
            row=2, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        self._pille(ie, "ps5pkg.exfat_edit_btn_folder", self._exfat_edit_ordner_waehlen, klein=True).grid(row=2, column=2, pady=(8, 0))
        self._exfat_edit_unpack_status = tk.Label(ie, text="", font=(F, pt(9)), bg=c["bg_card"],
                                                  fg=c["fg_secondary"], anchor="w", wraplength=540)
        self._exfat_edit_unpack_status.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._pille(ie, "ps5pkg.exfat_edit_btn_unpack", self._exfat_entpacken, akzent=True).grid(
            row=4, column=0, columnspan=3, pady=(8, 0), sticky="w")
        # Aufbauen-Bereich
        trennlinie = tk.Frame(ie, bg=c["border"], height=1)
        trennlinie.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        tk.Label(ie, text=t("ps5pkg.exfat_edit_lbl_source2"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=6, column=0, sticky="w", padx=(0, 8))
        self._exfat_edit_ordner2_var = tk.StringVar()
        pw.Entry(ie, textvariable=self._exfat_edit_ordner2_var, font=(F, pt(10))).grid(
            row=6, column=1, sticky="ew", padx=(0, 8))
        self._pille(ie, "ps5pkg.exfat_edit_btn_source2", self._exfat_edit_ordner2_waehlen, klein=True).grid(row=6, column=2)
        tk.Label(ie, text=t("ps5pkg.exfat_edit_lbl_target"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._exfat_edit_ziel_var = tk.StringVar()
        pw.Entry(ie, textvariable=self._exfat_edit_ziel_var, font=(F, pt(10))).grid(
            row=7, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        self._pille(ie, "ps5pkg.exfat_edit_btn_target", self._exfat_edit_ziel_waehlen, klein=True).grid(row=7, column=2, pady=(8, 0))
        self._exfat_edit_pack_status = tk.Label(ie, text="", font=(F, pt(9)), bg=c["bg_card"],
                                                fg=c["fg_secondary"], anchor="w", wraplength=540)
        self._exfat_edit_pack_status.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._pille(ie, "ps5pkg.exfat_edit_btn_pack", self._exfat_aufbauen, akzent=True).grid(
            row=9, column=0, columnspan=3, pady=(8, 0), sticky="w")

        # ---- FFPKG-Metadaten reparieren (Nr. 4) ----
        karte_ffpkg = self._karte(innen, "ps5pkg.ffpkg_repair_title")
        karte_ffpkg.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ifp = tk.Frame(karte_ffpkg, bg=c["bg_card"])
        ifp.pack(fill="both", expand=True)
        ifp.columnconfigure(1, weight=1)
        tk.Label(ifp, text=t("ps5pkg.ffpkg_repair_hint"), font=(F, pt(9)), bg=c["bg_card"],
                 fg=c["fg_secondary"], wraplength=540, justify="left", anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        tk.Label(ifp, text=t("ps5pkg.ffpkg_repair_lbl_file"), font=(F, pt(10)), bg=c["bg_card"],
                 fg=c["fg_primary"], anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._ffpkg_rep_pfad_var = tk.StringVar()
        pw.Entry(ifp, textvariable=self._ffpkg_rep_pfad_var, font=(F, pt(10))).grid(
            row=1, column=1, sticky="ew", padx=(0, 8))
        self._pille(ifp, "ps5pkg.ffpkg_repair_btn_file", self._ffpkg_rep_waehlen, klein=True).grid(row=1, column=2)
        self._ffpkg_rep_status = tk.Label(ifp, text="", font=(F, pt(9)), bg=c["bg_card"],
                                          fg=c["fg_secondary"], anchor="w", wraplength=540)
        self._ffpkg_rep_status.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._pille(ifp, "ps5pkg.ffpkg_repair_btn_copy", self._ffpkg_befehl_kopieren, akzent=True).grid(
            row=3, column=0, columnspan=3, pady=(12, 0), sticky="w")

    def _dds_quelle_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(parent=self.win, title=self.t("ps5pkg.dds_btn_source"),
                                          filetypes=[(self.t("ps5pkg.dds_filetype"), "*.dds"),
                                                     (self.t("filetype.all_files"), "*.*")])
        if pfad:
            pfad = os.path.normpath(pfad)
            self._dds_quelle_var.set(pfad)
            if not self._dds_ziel_var.get():
                basis = os.path.splitext(pfad)[0]
                self._dds_ziel_var.set(basis + ".png")

    def _dds_ziel_waehlen(self) -> None:
        start = self._dds_ziel_var.get()
        vorschlag = os.path.basename(start) if start else "ausgabe.png"
        pfad = filedialog.asksaveasfilename(parent=self.win, title=self.t("ps5pkg.dds_btn_target"),
                                             defaultextension=".png",
                                             filetypes=[("PNG", "*.png"), (self.t("filetype.all_files"), "*.*")],
                                             initialfile=vorschlag)
        if pfad:
            self._dds_ziel_var.set(os.path.normpath(pfad))

    def _dds_konvertieren(self) -> None:
        from ps5_validator.utils import sdk_werkzeuge as sdk
        werkzeug = sdk.dds2png_suchen(self._wurzeln())
        if not werkzeug:
            self._dds_status.configure(fg=self.c["fg_error"] if "fg_error" in self.c else "red",
                                       text=self.t("ps5pkg.dds_err_no_tool"))
            return
        quelle = self._dds_quelle_var.get().strip()
        ziel = self._dds_ziel_var.get().strip()
        if not quelle:
            self._dds_status.configure(text=self.t("ps5pkg.dds_err_no_source"))
            return
        if not ziel:
            self._dds_status.configure(text=self.t("ps5pkg.dds_err_no_target"))
            return
        self._dds_status.configure(text="…", fg=self.c["fg_secondary"])
        self.win.update_idletasks()
        try:
            sdk.dds_zu_png(werkzeug, quelle, ziel,
                           preserve_alpha=bool(self._dds_alpha_var.get()),
                           zeile=lambda z: self._dds_status.configure(text=z))
            self._dds_status.configure(fg=self.c["fg_secondary"],
                                       text=self.t("ps5pkg.dds_ok", datei=os.path.basename(ziel)))
        except sdk.Fehler as exc:
            self._dds_status.configure(fg=self.c.get("fg_error", "red"), text=str(exc))

    # -- exFAT Boot-Sektor reparieren (Nr. 3) --
    def _exfat_rep_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(parent=self.win, title=self.t("ps5pkg.exfat_repair_lbl_file"),
                                          filetypes=[("exFAT", "*.exfat"), (self.t("filetype.all_files"), "*.*")])
        if pfad:
            self._exfat_rep_pfad_var.set(os.path.normpath(pfad))

    def _exfat_reparieren(self) -> None:
        from ps5_validator.utils import exfat_werkzeuge as ew
        pfad = self._exfat_rep_pfad_var.get().strip()
        if not pfad:
            self._exfat_rep_status.configure(text=self.t("ps5pkg.exfat_repair_err_no_file"),
                                             fg=self.c.get("fg_error", "red"))
            return
        self._exfat_rep_status.configure(text="…", fg=self.c["fg_secondary"])
        self.win.update_idletasks()
        ok, marker = ew.exfat_boot_sektor_reparieren(pfad)
        if ok:
            msg = (self.t("ps5pkg.exfat_repair_ok_already") if marker == ew.MARKER_PRIMAER_OK
                   else self.t("ps5pkg.exfat_repair_ok_done"))
            self._exfat_rep_status.configure(text=msg, fg=self.c["fg_secondary"])
        else:
            self._exfat_rep_status.configure(text=self.t("ps5pkg.exfat_repair_err", fehler=marker),
                                             fg=self.c.get("fg_error", "red"))

    # -- exFAT-Inhalt bearbeiten (Nr. 2) --
    def _exfat_edit_quelle_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(parent=self.win, title=self.t("ps5pkg.exfat_edit_lbl_source"),
                                          filetypes=[("exFAT", "*.exfat"), (self.t("filetype.all_files"), "*.*")])
        if pfad:
            self._exfat_edit_quelle_var.set(os.path.normpath(pfad))

    def _exfat_edit_ordner_waehlen(self) -> None:
        ordner = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.exfat_edit_lbl_folder"))
        if ordner:
            self._exfat_edit_ordner_var.set(os.path.normpath(ordner))
            if not self._exfat_edit_ordner2_var.get():
                self._exfat_edit_ordner2_var.set(os.path.normpath(ordner))

    def _exfat_edit_ordner2_waehlen(self) -> None:
        ordner = filedialog.askdirectory(parent=self.win, title=self.t("ps5pkg.exfat_edit_lbl_source2"))
        if ordner:
            self._exfat_edit_ordner2_var.set(os.path.normpath(ordner))

    def _exfat_edit_ziel_waehlen(self) -> None:
        pfad = filedialog.asksaveasfilename(parent=self.win, title=self.t("ps5pkg.exfat_edit_lbl_target"),
                                            defaultextension=".exfat",
                                            filetypes=[("exFAT", "*.exfat"), (self.t("filetype.all_files"), "*.*")])
        if pfad:
            self._exfat_edit_ziel_var.set(os.path.normpath(pfad))

    def _exfat_entpacken(self) -> None:
        from ps5_validator.utils import exfat_werkzeuge as ew
        quelle = self._exfat_edit_quelle_var.get().strip()
        ordner = self._exfat_edit_ordner_var.get().strip()
        if not quelle:
            self._exfat_edit_unpack_status.configure(text=self.t("ps5pkg.exfat_edit_err_no_source"),
                                                     fg=self.c.get("fg_error", "red"))
            return
        if not ordner:
            self._exfat_edit_unpack_status.configure(text=self.t("ps5pkg.exfat_edit_err_no_folder"),
                                                     fg=self.c.get("fg_error", "red"))
            return
        if not ew.mkpfs_eltern_suchen(self._wurzeln()):
            self._exfat_edit_unpack_status.configure(text=self.t("ps5pkg.exfat_edit_err_no_tool"),
                                                     fg=self.c.get("fg_error", "red"))
            return
        self._exfat_edit_unpack_status.configure(text="…", fg=self.c["fg_secondary"])
        self.win.update_idletasks()
        ok, ausgabe = ew.exfat_entpacken(self._wurzeln(), quelle, ordner)
        if ok:
            self._exfat_edit_unpack_status.configure(
                text=self.t("ps5pkg.exfat_edit_ok_unpack", pfad=ordner), fg=self.c["fg_secondary"])
        else:
            self._exfat_edit_unpack_status.configure(
                text=self.t("ps5pkg.exfat_edit_err", fehler=ausgabe[:200]), fg=self.c.get("fg_error", "red"))

    def _exfat_aufbauen(self) -> None:
        from ps5_validator.utils import exfat_werkzeuge as ew
        ordner = self._exfat_edit_ordner2_var.get().strip()
        ziel = self._exfat_edit_ziel_var.get().strip()
        if not ordner:
            self._exfat_edit_pack_status.configure(text=self.t("ps5pkg.exfat_edit_err_no_folder"),
                                                   fg=self.c.get("fg_error", "red"))
            return
        if not ziel:
            self._exfat_edit_pack_status.configure(text=self.t("ps5pkg.exfat_edit_err_no_source"),
                                                   fg=self.c.get("fg_error", "red"))
            return
        if not ew.mkpfs_eltern_suchen(self._wurzeln()):
            self._exfat_edit_pack_status.configure(text=self.t("ps5pkg.exfat_edit_err_no_tool"),
                                                   fg=self.c.get("fg_error", "red"))
            return
        self._exfat_edit_pack_status.configure(text="…", fg=self.c["fg_secondary"])
        self.win.update_idletasks()
        ok, ausgabe = ew.exfat_aufbauen(self._wurzeln(), ordner, ziel)
        if ok:
            self._exfat_edit_pack_status.configure(
                text=self.t("ps5pkg.exfat_edit_ok_pack", pfad=ziel), fg=self.c["fg_secondary"])
        else:
            self._exfat_edit_pack_status.configure(
                text=self.t("ps5pkg.exfat_edit_err", fehler=ausgabe[:200]), fg=self.c.get("fg_error", "red"))

    # -- FFPKG-Metadaten reparieren (Nr. 4) --
    def _ffpkg_rep_waehlen(self) -> None:
        pfad = filedialog.askopenfilename(parent=self.win, title=self.t("ps5pkg.ffpkg_repair_lbl_file"),
                                          filetypes=[("FFPKG", "*.ffpkg"), (self.t("filetype.all_files"), "*.*")])
        if pfad:
            self._ffpkg_rep_pfad_var.set(os.path.normpath(pfad))

    def _ffpkg_befehl_kopieren(self) -> None:
        from ps5_validator.utils import werkzeuge_bereitstellen as wb
        pfad = self._ffpkg_rep_pfad_var.get().strip()
        if not pfad:
            self._ffpkg_rep_status.configure(text=self.t("ps5pkg.ffpkg_repair_err_no_file"),
                                             fg=self.c.get("fg_error", "red"))
            return
        try:
            wurzeln = self._wurzeln()
            def _suche(ordner_name: str) -> str:
                for w in wurzeln:
                    if os.path.isdir(os.path.join(w, ordner_name)):
                        return w
                return ""
            ufs2tool = wb.ufs2tool_bereitstellen(_suche)
        except Exception:
            ufs2tool = ""
        if not ufs2tool:
            self._ffpkg_rep_status.configure(text=self.t("ps5pkg.ffpkg_repair_err_no_tool"),
                                             fg=self.c.get("fg_error", "red"))
            return
        befehl = f'"{ufs2tool}" fsck_ufs -y "{pfad}"'
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(befehl)
        except Exception:
            pass
        self._ffpkg_rep_status.configure(text=self.t("ps5pkg.ffpkg_repair_copied"),
                                         fg=self.c["fg_secondary"])

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
                        info = wz.lesen(werkzeug, pfad, arbeit, passcode=self._passcode(), popen_extra=popen_extra)
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
        """Beim Oeffnen des Fensters gerufen - liest die gemerkte Bibliothek NICHT von selbst.

        Nutzerwunsch (18.10.2026): "Beim Oeffnen ... soll bitte nicht ... bereits
        etwas gescannt werden. Man soll bitte zuerst manuell waehlen muessen,
        erst dann soll gescannt werden." Bis dahin las ``_lesen_starten`` hier
        ungefragt jede gemerkte Paketdatei neu ein (Kopfdaten, ``param.json``,
        Cover) - bei vielen oder grossen Paketen sichtbar spuerbar, noch bevor
        irgendetwas gewaehlt wurde. Die gemerkte Liste bleibt gespeichert; ein
        Klick auf "Aktualisieren" (:meth:`_bibliothek_aktualisieren`) holt sie
        bei Bedarf nach - das ist die manuelle Wahl.
        """
        # Option "Bibliothek beim Start aktualisieren": die Bibliotheksordner neu durchsuchen
        if self._einstellung(opt.START_SCAN, False) is True:
            ordner = self._einstellung(opt.ORDNER, [])
            if isinstance(ordner, list) and ordner:
                self._ordner_scan_starten([o for o in ordner if isinstance(o, str)],
                                          self._einstellung(opt.REKURSIV, False) is True)

    # ------------------------------------------------------------------
    # Optionen (Dialog: ps5_pkg_optionen)
    # ------------------------------------------------------------------
    def _optionen_oeffnen(self) -> None:
        optionen_ui.oeffnen(self)

    def _cover_an(self) -> bool:
        return self._einstellung(opt.COVER, True) is not False

    def _passcode(self) -> str:
        wert = self._einstellung(opt.PASSCODE, "")
        return wert if isinstance(wert, str) and wz.passcode_gueltig(wert) else ""

    def _builder(self) -> str:
        """Welches Werkzeug "Paket bauen" verwendet - nur "lpp" oder "ppt" (siehe opt.BUILDER)."""
        wert = self._einstellung(opt.BUILDER, "lpp")
        return wert if wert in opt.BUILDER_WERTE else "lpp"

    def _ordner_scan_starten(self, ordner: list[str], rekursiv: bool) -> None:
        """Durchsucht die Bibliotheksordner im Hintergrund; neue Quellen traegt der Takt danach ein."""
        ordner = [o for o in ordner if os.path.isdir(o)]
        if not ordner:
            return

        def lauf() -> None:
            gefunden: list[str] = []
            for o in ordner:
                try:
                    gefunden.extend(opt.ordner_durchsuchen(o, wz.ordner_ist_spiel) if rekursiv else self._quellen_in(o))
                except Exception:  # noqa: BLE001 - ein unlesbarer Ordner darf die anderen nicht aufhalten
                    logger.exception("Bibliotheksordner %s", o)
            with self._sperre:
                self._z["scan"].append(gefunden)

        threading.Thread(target=lauf, daemon=True, name="ps5pkg-scan").start()

    def _scan_uebernehmen(self, ergebnisse: list[list[str]]) -> None:
        bekannt = {i.pfad for i in self.pakete}
        neu: list[str] = []
        for liste in ergebnisse:
            for pfad in liste:
                if pfad not in bekannt and pfad not in neu:
                    neu.append(pfad)
        if neu and self._werkzeug():
            self._lesen_starten(neu)
            self._protokoll(self.t("ps5pkg.opt_scan_found", count=len(neu)))
        else:
            self._status(self.t("ps5pkg.opt_scan_none"))

    def optionen_anwenden(self, werte: dict, alt: dict, entfernt: list[str], neue_quellen: list[str]) -> None:
        """Speichert die Optionen und setzt sie gleich um (vom Dialog beim Speichern gerufen)."""
        for schluessel in (opt.ORDNER, *opt.STANDARD):
            self._merken(schluessel, werte[schluessel])
        if entfernt:
            self.pakete = [i for i in self.pakete if i.pfad not in entfernt]
            self._bibliothek_speichern()
            if self.aktuell is not None and self.aktuell.pfad in entfernt:
                self.aktuell = None
                self.paket_titel.configure(text=self.t("ps5pkg.no_source"))
                self.paket_pfad.configure(text="")
                self.paket_typ.configure(text="")
                self.paket_playgo.configure(text="")
                self._cover = None
                self.cover_label.configure(image="", text=self.t("ps5pkg.no_cover"))
                spielinfo_zuruecksetzen(self.g)
                if self.pakete:
                    self._paket_waehlen(gewaehlen_info=self.pakete[0])
        laeuft = self._job is not None or self._uebergabe is not None
        if not laeuft:
            if werte[opt.ZIEL] != alt[opt.ZIEL]:
                self.ziel_var.set(werte[opt.ZIEL])
            if werte[opt.AKTION] != alt[opt.AKTION] and self._aktion_moeglich(werte[opt.AKTION]):
                self.aktion_var.set(werte[opt.AKTION])
                self._aktion_geaendert()
            if werte[opt.FORMAT] != alt[opt.FORMAT] and self._format_moeglich(werte[opt.FORMAT]):
                self.format_schluessel = werte[opt.FORMAT]
                self._kacheln_faerben()
        if self.aktuell is not None:
            self._cover_zeigen(self.aktuell)
            self._spielinfo_zeigen(self.aktuell)
        self._liste_fuellen(auswaehlen=self.aktuell.pfad if self.aktuell is not None else "")
        self._knoepfe_pruefen()
        if werte[opt.ORDNER] and (werte[opt.ORDNER] != alt[opt.ORDNER] or werte[opt.REKURSIV] != alt[opt.REKURSIV]):
            self._ordner_scan_starten(werte[opt.ORDNER], werte[opt.REKURSIV])
        if neue_quellen and self._werkzeug():
            self._pakete_hinzufuegen(neue_quellen)
        self._status(self.t("ps5pkg.opt_saved"))

    def _ausgabe_nach_erfolg(self) -> None:
        """Option "Ausgabeordner nach erfolgreichem Auftrag oeffnen"."""
        if self._einstellung(opt.OEFFNEN, False) is True:
            self._ausgabe_oeffnen()

    def _bibliothek_aktualisieren(self) -> None:
        """Der Knopf AKTUALISIEREN - die manuelle Wahl, die das Lesen auslöst.

        Steht noch nichts in der Liste (frischer Fensterstart, siehe
        :meth:`_bibliothek_laden`), kommt die zuletzt gemerkte Bibliothek von
        hier zurueck - ein bewusster Klick statt eines ungefragten Lesens beim
        Oeffnen.
        """
        if self.pakete:
            pfade = [i.pfad for i in self.pakete if os.path.exists(i.pfad)]
            self.pakete = []
            self._liste_fuellen()
        else:
            gemerkt = self._einstellung(EINST_BIBLIOTHEK, [])
            pfade = [p for p in gemerkt if isinstance(p, str) and os.path.exists(p)] \
                if isinstance(gemerkt, list) else []
        if pfade and self._werkzeug():
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
        sortierung = self._einstellung(opt.SORTIERUNG, "titel")
        if sortierung == "titel_id":
            reihenfolge = lambda i: (i.title_id or "~", (i.titel or i.pfad).lower())          # noqa: E731
        elif sortierung == "groesse":
            reihenfolge = lambda i: (-int(i.groesse or 0), (i.titel or i.pfad).lower())       # noqa: E731
        else:
            reihenfolge = lambda i: (i.titel or i.pfad).lower()                               # noqa: E731
        for info in sorted(self.pakete, key=reihenfolge):
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
        # PlayGo-Hinweis: Ordner direkt, Archive im Hintergrund (Subprocess).
        if info.ist_ordner:
            merkmal = wz.playgo_erklaert_ordner(info.pfad)
            self.paket_playgo.configure(
                text=self.t("pkg.playgo_hinweis", datei=merkmal) if merkmal else "")
        else:
            self.paket_playgo.configure(text="")
            ext = os.path.splitext(info.pfad)[1].lower()
            if ext in (".pkg", ".ffpfsc", ".ffpfs", ".exfat", ".ffpkg"):
                pfad_snap = info.pfad
                def _pruefe_archiv_playgo(p=pfad_snap):
                    merkmal = wz.playgo_erklaert_archiv(p, self._werkzeug(), self._wurzeln())
                    def _ui():
                        if hasattr(self, "paket_playgo") and self.aktuell and self.aktuell.pfad == p:
                            self.paket_playgo.configure(
                                text=self.t("pkg.playgo_hinweis", datei=merkmal) if merkmal else "")
                    try:
                        self.after(0, _ui)
                    except Exception:
                        pass
                import threading as _threading
                _threading.Thread(target=_pruefe_archiv_playgo, daemon=True).start()
        # Was fuer diese Quelle nicht geht, springt auf den Vorgabewert zurueck (ohne es zu speichern).
        if not self._aktion_moeglich(self.aktion_var.get()):
            self.aktion_var.set(AKTION_UMWANDELN)
        if not self._format_moeglich(self.format_schluessel):
            self.format_schluessel = "ffpfsc"
        self._aktion_anwenden()
        self._cover_zeigen(info)
        self._spielinfo_zeigen(info)
        self.tech.delete(*self.tech.get_children())
        for eig, wert in uebersicht(info, self.t, self._fmt):
            self.tech.insert("", "end", values=(eig, wert))
        if not aus_liste and self.liste.exists(info.pfad):
            self.liste.selection_set(info.pfad)
        self._knoepfe_pruefen()

    def _cover_zeigen(self, info: "wz.PaketInfo") -> None:
        self._cover = None
        an = self._cover_an()
        if an and info.icon and os.path.isfile(info.icon):
            try:
                from PIL import Image, ImageDraw, ImageTk
                bild = Image.open(info.icon).convert("RGBA")
                bild.thumbnail((330, 330))
                # Abgerundete Ecken: ausserhalb der Rundung ist das Bild durchsichtig, dahinter steht der Kartengrund.
                maske = Image.new("L", bild.size, 0)
                ImageDraw.Draw(maske).rounded_rectangle((0, 0, bild.width - 1, bild.height - 1), radius=16, fill=255)
                bild.putalpha(maske)
                self._cover = ImageTk.PhotoImage(bild, master=self.win)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Cover nicht lesbar: %s", exc)
        if self._cover is not None:
            self.cover_label.configure(image=self._cover, text="", compound="center")
            self.cover_label.configure(height=300)
        else:
            text = self.t("ps5pkg.no_cover") if an else ""        # ausgeschaltet: nichts anzeigen, auch keinen Hinweis
            self.cover_label.configure(image="", text=text)

    def _spielinfo_zeigen(self, info: "wz.PaketInfo") -> None:
        """Cover, Titel und Metadaten des gewaehlten Pakets in die Seitenleiste und das Fenster "Spiel Info - Updates &
        Patches": derselbe Weg (``_update_info_box``) wie bei den Aufgaben 1 bis 6 (Nutzerwunsch 13.10.2026)."""
        g = self.g
        try:
            meta = dict(g._meta_from_param_json_payload(info.param)) if info.param else {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Metadaten des Pakets nicht lesbar: %s", exc)
            meta = {}
        for schluessel, wert in (("title", info.titel), ("title_id", info.title_id), ("content_id", info.content_id)):
            if wert and str(meta.get(schluessel, "") or "–") in ("–", "-", ""):
                meta[schluessel] = wert
        meta["_metadata_method"] = self.t("ps5pkg.meta_method")
        cover = None
        if self._cover_an() and info.icon and os.path.isfile(info.icon):
            try:
                from PIL import Image
                cover = Image.open(info.icon).convert("RGBA")
                cover.load()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Cover fuer die Seitenleiste nicht lesbar: %s", exc)
                cover = None
        g._update_info_box(meta, cover, self._fmt(info.groesse), "")
        # Was die Info-Box aus der Quelle der Aufgaben 1 bis 6 liest, gehoert nicht zu diesem Paket.
        for schluessel in ("sdk_stand", "ampr_emu"):
            if schluessel in g._meta_labels:
                g._meta_labels[schluessel].set("–")
        g._info_format_var.set(self.t("ps5pkg.badge_folder") if info.ist_ordner
                               else self.t("ps5pkg.badge_debug") if info.debug else (info.typ or "–"))

    def spielinfo_nachziehen(self) -> None:
        """Zeigt die Angaben des gewaehlten Pakets erneut, wenn die Seite wieder erscheint.

        Der Wechsel zu Aufgabe 7 loest ueber ``current_mode`` eine Neuberechnung der Quelle aus (verzoegert um 180 ms),
        die Seitenleiste und Info-Box leert - deshalb kommt diese Anzeige kurz danach noch einmal."""
        def _lauf() -> None:
            try:
                if self.win.winfo_exists() and self.aktuell is not None and self.win.winfo_ismapped():
                    self._spielinfo_zeigen(self.aktuell)
            except tk.TclError:
                pass
        self.win.after(400, _lauf)

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
        aktion = self.aktion_var.get()
        if aktion == AKTION_PRUEFEN:
            v["output"].set("-")
        elif aktion == AKTION_KONSOLE:
            v["output"].set("%s:%s" % (self.adresse_var.get().strip() or "?", "/" + self.fern_var.get().strip().strip("/")))
        else:
            v["output"].set(self._ziel_name())
        v["title_id"].set(info.title_id)
        v["content"].set(info.content_id)
        v["size"].set("ca. " + self._fmt(info.groesse))
        ziel = self.ziel_var.get().strip()
        frei = ""
        try:
            if ziel and os.path.isdir(ziel) and aktion != AKTION_KONSOLE:
                frei = self._fmt(shutil.disk_usage(ziel).free)
        except OSError:
            frei = ""
        v["free"].set(frei)

    def _aktion_geaendert(self) -> None:
        """Der Anwender hat die Aktion gewaehlt: anwenden und merken."""
        self._merken(EINST_AKTION, self.aktion_var.get())
        self._aktion_anwenden()

    def _konsole_zeilen_zeigen(self) -> None:
        """Bei der Aktion "Auf die PS5 entpacken" stehen Adresse und Ordner der Konsole statt des Zielordners auf dem PC."""
        konsole = self.aktion_var.get() == AKTION_KONSOLE
        if konsole == self._konsole_ansicht or not hasattr(self, "fern_reihe"):
            return
        self._konsole_ansicht = konsole
        try:
            if konsole:
                self.ziel_reihe.pack_forget()
                self.ueberschreiben.pack_forget()
                self.fern_reihe.pack(fill="x", pady=(10, 0), after=self.aktion_reihe)
            else:
                self.fern_reihe.pack_forget()
                self.ziel_reihe.pack(fill="x", pady=(10, 0), after=self.aktion_reihe)
                self.ueberschreiben.pack(anchor="w", pady=(6, 0), after=self.ziel_reihe)
        except tk.TclError as exc:
            logger.debug("Zeilen der Aktion nicht umschaltbar: %s", exc)

    def _aktion_anwenden(self) -> None:
        """Kacheln, Ergebnis und Knoepfe zur Aktion nachziehen - ohne zu speichern (auch beim Oeffnen)."""
        for aktion, knopf in getattr(self, "_aktion_knoepfe", {}).items():
            try:
                knopf.configure(state="normal" if self._aktion_moeglich(aktion) else "disabled")
            except tk.TclError:
                pass
        self._konsole_zeilen_zeigen()
        self._kacheln_faerben()
        self._ergebnis_fuellen()
        self._knoepfe_pruefen()

    def _knoepfe_pruefen(self) -> None:
        laeuft = self._job is not None or self._uebergabe is not None
        # Datei-Browser nur fuer .pkg-Dateien (list-inner braucht ein Paket, keinen Ordner)
        browser_ok = (self.aktuell is not None and not self.aktuell.ist_ordner
                      and bool(self._werkzeug()))
        # Detail-Fenster nur fuer Spielordner
        detail_ok = self.aktuell is not None and bool(self.aktuell.ist_ordner)
        try:
            self.start_knopf.configure(state="disabled" if (laeuft or self.aktuell is None) else "normal")
            self.abbrechen_knopf.configure(state="normal" if laeuft else "disabled")
            self.cover_knopf.configure(state="normal" if self.aktuell is not None else "disabled")
            self.browser_knopf.configure(state="normal" if browser_ok else "disabled")
            self.detail_knopf.configure(state="normal" if detail_ok else "disabled")
        except tk.TclError:
            pass

    def _fehler(self, text: str) -> None:
        self._protokoll(text)
        messagebox.showerror(self.t("ps5pkg.window_title"), text, parent=self.win)

    def _browser_oeffnen(self) -> None:
        """Oeffnet den Datei-Browser fuer das aktuell gewaehlte .pkg-Paket."""
        if self.aktuell is None or self.aktuell.ist_ordner:
            return
        vorh = getattr(self.win, browser_ui.FENSTER_ATTRIBUT, None)
        if vorh is not None:
            try:
                vorh.win.lift()
                vorh.win.focus_set()
                return
            except tk.TclError:
                pass
        browser_ui.PkgDateiBrowser(self.win, self, self._werkzeug(),
                                    self.aktuell.pfad, passcode=self._passcode())

    def _detail_oeffnen(self) -> None:
        """Oeffnet das Spiel-Detail-Fenster fuer den aktuell gewaehlten Spielordner."""
        if self.aktuell is None or not self.aktuell.ist_ordner:
            return
        vorh = getattr(self.win, detail_ui.FENSTER_ATTRIBUT, None)
        if vorh is not None:
            try:
                vorh.win.lift()
                vorh.win.focus_set()
                return
            except tk.TclError:
                pass
        detail_ui.SpielDetailFenster(self.win, self, self.aktuell.pfad, titel=self.aktuell.titel or "")

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
        if aktion == AKTION_KONSOLE:
            self._konsole_starten(info)
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

    def _konsole_starten(self, info: "wz.PaketInfo") -> None:
        """Prueft Adresse und Ordner und startet das Entpacken auf die PS5 (der Arbeitsfaden fragt und sendet)."""
        adresse = self.adresse_var.get().strip()
        fern = "/" + self.fern_var.get().strip().strip("/")
        if not adresse:
            self._fehler(self.t("ps5pkg.err_no_address"))
            return
        if fern == "/":                         # die Wurzel der Konsole ist kein Ziel fuer ein Spiel
            self._fehler(self.t("ps5pkg.err_no_remote"))
            return
        self._merken(EINST_FERN, fern)
        self.fern_var.set(fern)
        self._konsole_ziel = (adresse, fern)
        self._job_starten("konsole", self._lauf_konsole, info, fern)

    def _platz_fuer_entpacken(self, ziel: str, gesamt: int) -> str:
        """Arbeitsfaden: reicht der Platz fuer das entpackte Spiel (``gesamt`` Bytes, aus dem Paketinhalt)? "" = ja.

        Die Schaetzung vor dem Start (Paketgroesse x ENTPACKT_FAKTOR) kennt die Kompression nicht: Fuer LEGO Batman
        nannte sie 54 GB, entpackt waren es 110 GB (14.10.2026). Hier steht die echte Zahl fest.
        """
        ordner = ziel
        while ordner and not os.path.isdir(ordner):
            ordner = os.path.dirname(ordner)
        try:
            frei = int(shutil.disk_usage(ordner or ziel).free)
        except OSError:
            return ""
        noetig = int(gesamt) + (1 << 30)
        if frei >= noetig:
            return ""
        return self.t("ps5pkg.err_space_unpacked", ordner=ordner, frei=self._fmt(frei), noetig=self._fmt(noetig))

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
        if self._builder() == "ppt" and not self._werkzeug_ppt():
            self._fehler(self.t("ps5pkg.err_no_tool_ppt"))
            return
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
                "umwandeln": "ps5pkg.job_extracting_for", "bauen": "ps5pkg.job_building",
                "konsole": "ps5pkg.job_console"}[art]
        self.auftrag_var.set(self.t(text, name=anzeigename(info)))
        self._protokoll(self.t("ps5pkg.log_start_" + art, name=os.path.basename(info.pfad)))
        self._knoepfe_pruefen()
        threading.Thread(target=ziel_funktion, args=(info, ziel, art), daemon=True, name="ps5pkg-" + art).start()

    def _lauf_pruefen(self, info: "wz.PaketInfo", _ziel: str, _art: str) -> None:
        try:
            ergebnis = wz.pruefen(self._werkzeug(), info.pfad, passcode=self._passcode(), abbruch=lambda: self._abbruch,
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
            if self._builder() == "ppt":
                werkzeug_ppt = self._werkzeug_ppt()
                if not werkzeug_ppt:
                    raise wz.Fehler(self.t("ps5pkg.err_no_tool_ppt"))
                ppt.extrahieren(werkzeug_ppt, info.pfad, ziel, passcode=self._passcode(), zeile=self._melden,
                                abbruch=lambda: self._abbruch, popen_extra=self._popen_extra())
                schluss = self.t("ps5pkg.log_extracted", anzahl="?")
            else:
                schluss = wz.extrahieren(self._werkzeug(), info.pfad, ziel, passcode=self._passcode(),
                                         zeile=self._melden, fortschritt=fortschritt,
                                         abbruch=lambda: self._abbruch, popen_extra=self._popen_extra(),
                                         platz_pruefen=lambda gesamt: self._platz_fuer_entpacken(ziel, gesamt))
            ende = {"ok": True, "text": schluss, "ausgabe": ziel}
        except wz.Fehler as exc:
            ende = {"ok": False, "text": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket entpacken")
            ende = {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        with self._sperre:
            self._z["fertig"] = ende

    def _lauf_konsole(self, info: "wz.PaketInfo", fern: str, art: str) -> None:
        """Arbeitsfaden: das Paket direkt auf die PS5 entpacken (:func:`pkg_direkt.direkt_entpacken`).

        Die Rueckfragen laufen ueber den Fensterfaden (``_im_hauptfaden``), der Faden selbst fasst kein Widget an.
        Liegt das Ziel schon auf der Konsole, entscheidet der Anwender zwischen Fortsetzen (fertige Dateien
        ueberspringen, angefangene weiterschreiben), alles neu schreiben und Abbrechen; sonst bestaetigt er Groesse und
        Dauer. Abgebrochen wird nach der laufenden Datei.
        """
        adresse = self._konsole_ziel[0]
        titel = self.t("ps5pkg.window_title")

        def fortschritt(stand) -> None:
            with self._sperre:
                self._z["prozent"] = stand.anteil * 100.0
                self._z["schritt_text"] = self.t(
                    "ps5pkg.console_status", datei=stand.aktuell, dateien=min(stand.dateien + 1, stand.dateien_gesamt),
                    gesamt=stand.dateien_gesamt, menge=ftp.menge_lesbar(stand.bytes))

        try:
            if ftp.vorhanden(adresse, fern):
                antwort = self.g._im_hauptfaden(messagebox.askyesnocancel, titel,
                                                self.t("ps5pkg.ask_console_exists", ziel=fern), default="cancel",
                                                parent=self.win)
                if antwort is None:
                    with self._sperre:
                        self._z["fertig"] = {"ok": True, "nichts": True, "text": self.t("ps5pkg.console_nothing")}
                    return
                fortsetzen = bool(antwort)
            else:
                minuten = max(1, int(ftp.dauer_schaetzen(info.groesse, ftp.TEMPO_HOCH) / 60))
                if not self.g._im_hauptfaden(
                        messagebox.askyesno, titel,
                        self.t("ps5pkg.ask_console", name=anzeigename(info), ziel="%s:%s" % (adresse, fern),
                               menge=self._fmt(info.groesse), tempo=ftp.tempo_lesbar(ftp.TEMPO_HOCH), minuten=minuten),
                        default="no", parent=self.win):
                    with self._sperre:
                        self._z["fertig"] = {"ok": True, "nichts": True, "text": self.t("ps5pkg.console_nothing")}
                    return
                fortsetzen = False
            stand = pkg_direkt.direkt_entpacken(
                self._werkzeug(), info.pfad, adresse, fern, fortsetzen=fortsetzen, passcode=self._passcode(),
                auf_fortschritt=fortschritt, abbruch=lambda: self._abbruch, zeile=self._melden,
                popen_extra=self._popen_extra(), arbeitsordner=self._arbeitsordner())
            if stand.abgebrochen:
                ende = {"ok": True, "abgebrochen": True,
                        "text": self.t("ps5pkg.log_console_cancelled", dateien=stand.dateien, ziel=fern)}
            else:
                ende = {"ok": True, "text": self.t(
                    "ps5pkg.log_console_done", dateien=stand.dateien, menge=ftp.menge_lesbar(stand.bytes), ziel=fern,
                    uebersprungen=stand.uebersprungen, fortgesetzt=stand.fortgesetzt, wiederholt=stand.wiederholt)}
        except (ftp.FtpFehler, wz.Fehler) as exc:
            ende = {"ok": False, "text": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket auf die PS5 entpacken")
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

        _min_fw_alt: "str | None" = None
        _content_type_alt: "str | None" = None
        try:
            passcode = self._passcode()
            if self._builder() == "ppt":
                werkzeug_ppt = self._werkzeug_ppt()
                if not werkzeug_ppt:
                    raise wz.Fehler(self.t("ps5pkg.err_no_tool_ppt"))
                # Anders als wz.bauen() (LibProsperoPkg) nimmt ppt.bauen() keinen ZielORDNER - "ziel" geht
                # unveraendert als --out an ProsperoPkgTool, das dort eine DATEI oeffnet. Ein Ordnerpfad endete
                # deshalb immer mit "Access to the path '...' is denied" (das Werkzeug kam bis zum letzten
                # Schritt durch und scheiterte erst beim Schreiben; Durchsicht 17.10.2026 an einem echten Bau).
                ppt_datei = os.path.join(ziel, anzeigename(info) + ".pkg")
                pfad = ppt.bauen(werkzeug_ppt, info.pfad, ppt_datei, content_id=info.content_id, title_id=info.title_id,
                                 passcode=passcode, zeile=self._melden, fortschritt=fortschritt,
                                 abbruch=lambda: self._abbruch, popen_extra=self._popen_extra())
            else:
                min_fw_str = str(self._einstellung(opt.MIN_FW_VERSION, "")).strip()
                min_fw_hex = wz.fw_hex(min_fw_str) if min_fw_str else ""
                if min_fw_hex:
                    try:
                        _min_fw_alt = wz.param_json_setzen(
                            info.pfad, "requiredSystemSoftwareVersion", min_fw_hex)
                    except wz.Fehler as exc:
                        raise wz.Fehler(self.t("ps5pkg.err_min_fw_write", error=str(exc))) from exc
                if bool(self._einstellung(opt.PATCH_MODUS, False)):
                    try:
                        _content_type_alt = wz.param_json_setzen(info.pfad, "contentType", "PATCH")
                    except wz.Fehler as exc:
                        raise wz.Fehler(self.t("ps5pkg.err_patch_modus_write", error=str(exc))) from exc
                backport_an = bool(self._einstellung(opt.BACKPORT_EINBAUEN, False))
                if backport_an:
                    from ps5_validator.utils import ps5_pkg_backport as bp_util
                    fw = int(self._einstellung(opt.BACKPORT_FIRMWARE, 0))
                    fakelib_konfiguriert = str(self._einstellung(opt.BACKPORT_FAKELIB_ORDNER, "")).strip()
                    fakelib_basis = (fakelib_konfiguriert if fakelib_konfiguriert and os.path.isdir(fakelib_konfiguriert)
                                     else getattr(self.g, "_backport_fakelib_basis", lambda: "")())
                    erg, meldung = bp_util.backport_einbauen(
                        info.pfad, fw, fakelib_basis, zeile=self._melden, abbruch=lambda: self._abbruch)
                    if erg == bp_util.ERGEBNIS_ABGEBROCHEN:
                        raise wz.Fehler("abgebrochen")
                    if erg == bp_util.ERGEBNIS_FEHLER:
                        raise wz.Fehler(self.t("ps5pkg.err_backport", error=meldung))
                pfad = wz.bauen(self._werkzeug(), info.pfad, ziel, content_id=info.content_id, title_id=info.title_id,
                                titel=info.titel, version=str(param.get("contentVersion", "") or "01.000.000"),
                                modus=self._einstellung(opt.KRAKEN_MODUS, "kraken"),
                                stufe=int(self._einstellung(opt.KRAKEN_STUFE, 7)),
                                kerne=int(self._einstellung(opt.KRAKEN_KERNE, 0)),
                                playgo_chunks=int(self._einstellung(opt.PLAYGO_CHUNKS, 1)),
                                deterministisch=bool(self._einstellung(opt.DETERMINISTISCH, False)),
                                regen_playgo=bool(self._einstellung(opt.REGEN_PLAYGO, False)),
                                passcode=passcode, temp=bau.get("temp"), zeile=self._melden, fortschritt=fortschritt,
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
                erg = wz.pruefen(self._werkzeug(), pfad, passcode=passcode, abbruch=lambda: self._abbruch,
                                popen_extra=self._popen_extra())
                for r in erg.get("results", []):
                    if str(r.get("Level", "")) != "pass":
                        self._melden("[%s] %s: %s" % (str(r.get("Level", "")).upper(), r.get("Check", ""), r.get("Message", "")))
                pruef = self.t("ps5pkg.check_summary", ok=erg.get("pass", 0), warn=erg.get("warn", 0),
                               fail=erg.get("fail", 0))
                befund = int(erg.get("fail", 0)) > 0
            except wz.Fehler as exc:
                pruef, befund = str(exc), True
            ende = {"ok": True, "text": pfad, "ausgabe": ziel, "pkg": pfad, "pruefung": pruef, "befund": befund}
        finally:
            if _min_fw_alt is not None:
                try:
                    wz.param_json_setzen(info.pfad, "requiredSystemSoftwareVersion", _min_fw_alt)
                except wz.Fehler:
                    pass
            if _content_type_alt is not None:
                try:
                    wz.param_json_setzen(info.pfad, "contentType", _content_type_alt)
                except wz.Fehler:
                    pass
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
            scan, self._z["scan"] = self._z["scan"], []
        for z in zeilen:
            self._protokoll(z)
        if scan:
            self._scan_uebernehmen(scan)
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
                # Nur der Dateiname, nicht der Ordnerpfad im Spiel - sonst lief die Zeile rechts aus der Karte.
                erster, _trenner, rest = datei.partition(" \u00b7 ")
                kurz = erster.replace("\\", "/").rsplit("/", 1)[-1] or erster
                self.datei_var.set(kurz + (" \u00b7 " + rest if rest else ""))
        if fertig is not None and self._job is not None:
            self.datei_var.set("")
            self._job_beendet(fertig)
        if self._uebergabe is not None:
            self._uebergabe_beobachten()

    def _job_beendet(self, ende: dict) -> None:
        job, self._job = self._job, None
        art = job["art"]
        if ende.get("nichts") or ende.get("abgebrochen"):
            # Der Anwender hat bei der Rueckfrage verzichtet oder nach einer Datei abgebrochen: kein Fehlschlag.
            self.auftrag_var.set(ende["text"])
            self._protokoll(ende["text"])
            if ende.get("nichts"):
                self.balken["value"] = 0
                self.balken_gesamt["value"] = 0
            self._knoepfe_pruefen()
            return
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
        if art == "konsole":
            self.auftrag_var.set(self.t("ps5pkg.job_done_console", ziel=job["ziel"]))
            self._protokoll(ende["text"])
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
            self._ausgabe_nach_erfolg()
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
            self._ausgabe_nach_erfolg()
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
        dialog = getattr(self, optionen_ui.DIALOG_ATTRIBUT, None)
        if dialog is not None:
            dialog.schliessen()
        self._cover = None
        for ordner in self._cover_ordner:
            try:
                _haupt(self.g)._rmtree_force(ordner, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
        if getattr(self.g, FENSTER_ATTRIBUT, None) is self:
            setattr(self.g, FENSTER_ATTRIBUT, None)


def spielinfo_zuruecksetzen(gui) -> None:
    """Nimmt die Angaben dieser Seite aus Seitenleiste und Info-Box und laesst das Programm die Quelle der gewaehlten
    Aufgabe neu lesen (derselbe Weg wie bei einem Wechsel der Quelle)."""
    try:
        gui._last_preview_ctx = None
        gui._on_source_path_changed()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Spiel Info nicht zuruecksetzbar: %s", exc)


def oeffnen(gui, schrift: str, mono: str, pt: Callable[[int], int], vorgabe: str = "",
            *, master: "tk.Misc | None" = None) -> Ps5PkgFenster:
    """Gibt die Seite zurueck - einmalig gebaut, danach immer dieselbe (mit der neuen Vorgabe, falls es eine gibt).

    ``master``: wohin die Seite (einmalig) gebaut wird, siehe :func:`ps5_validator.ui.ps4_dump_image.oeffnen`.
    """
    vorhanden = getattr(gui, FENSTER_ATTRIBUT, None)
    if vorhanden is not None:
        try:
            if vorhanden.win.winfo_exists():
                if vorgabe:
                    vorhanden._pakete_hinzufuegen([p for p in vorgabe.split(os.pathsep) if p.strip()], waehlen=True)
                return vorhanden
        except tk.TclError:
            pass
    fenster = Ps5PkgFenster(gui, schrift, mono, pt, vorgabe, master=master)
    setattr(gui, FENSTER_ATTRIBUT, fenster)
    return fenster
