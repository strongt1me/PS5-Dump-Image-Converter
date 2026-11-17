# -*- coding: utf-8 -*-
"""Die Seite „FPKG“ unter Aufgabe 7 „PKG / FPKG“ (seit v1.9.71 bis 12.10.2026 abends ein eigenes Fenster unter
WEITERE TOOLS: „PS5 PKG Dump & Image Converter“).

Eine Oberflaeche in Karten nach dem Vorbild von PS5-PKG-IMAGE-CONVERTER 1.5.3 (Nutzerwunsch 08.10.2026):

* **Umwandeln** - Quelle (ein PS5-Paket ``.pkg`` oder ein Spielordner, per Ablegen oder Klick), Aktion (Erstellen /
  Umwandeln, Extrahieren, Pruefen), Zielformat als Auswahlfeld, Auftrag mit Fortschritt, rechts das Ergebnis.
* **Bibliothek** - die Pakete und Spielordner mit Suche, Cover und technischer Uebersicht.

Die Arbeit am Paket macht ``ffpfsc-pkg-tool`` (:mod:`ps5_validator.utils.ps5_pkg_werkzeug`): lesen, pruefen,
entpacken, bauen. **Umwandeln** eines Pakets entpackt das Spiel in einen Arbeitsordner und uebergibt ihn an
**Aufgabe 1** des Hauptprogramms (``pack_folder`` mit dem gewaehlten Zielformat) - so gelten dort dieselben
Pruefungen, derselbe Fortschritt und die Haken fuer AMPR EMU und BACKPORT; ein Spielordner geht ohne Entpacken
direkt dorthin. **Extrahieren** schreibt den Dump-Ordner direkt ins Ziel. Das Format **Paket** baut aus einem
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
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

from ps5_validator.utils import bibliothek_raster as raster
from ps5_validator.utils import forge_cli as forge
from ps5_validator.utils import konsole_ftp as ftp
from ps5_validator.utils import pkg_direkt
from ps5_validator.utils import ps5_pkg_optionen as opt
from ps5_validator.utils import ps5_pkg_werkzeug as wz
from ps5_validator.utils import quelle_loeschen
from ps5_validator.utils import quellbericht as qb
from ps5_validator.ui import hauptknoepfe
from ps5_validator.ui import pkg_einbau_karte as einbau_ui
from ps5_validator.ui import ps5_pkg_optionen as optionen_ui
from ps5_validator.ui import pkg_datei_browser as browser_ui
from ps5_validator.ui import spiel_detail_fenster as detail_ui

logger = logging.getLogger("PS5Converter.ui.ps5_pkg_fenster")

FENSTER_ATTRIBUT = "_ps5_pkg_fenster"
TAKT_MS = 250

#: Welche Reiter die Seite oben zeigt. Nutzerwunsch 30.10.2026: Bibliothek und Extras nicht mehr anzeigen - und weil
#: die Seite wie die Aufgaben 1 bis 6 aus einer Spalte besteht (Quellfeld im Kopf der Seite ``pkg_fpkg_seite``), gar keine
#: Reiterzeile mehr; "Optionen" ist ein Knopf der Knopfleiste. Die Seiten ``bibliothek`` und ``extras`` werden weiter
#: gebaut und ihr Code ist unveraendert - nur ihr Reiter fehlt. Zurueckholen: die Namen wieder in dieses Tupel schreiben.
SICHTBARE_REITER = ()

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
#: Bei diesen Formaten nennt das Fenster nach der Wahl das Tempo der Entpackung auf der Konsole (``main.pfs_speed_hint``).
FORMATE_MIT_RUCKELHINWEIS = ("ffpfsc", "ffpfs")

#: Ein entpacktes Spiel ist groesser als sein Paket (gemessen: 939 MB -> 1,55 GB).
ENTPACKT_FAKTOR = 1.7
#: Dump Forge legt keine Kopie an und liest Abbilder ohne Zwischenordner; das Paket wird nur so gross wie das Spiel
#: (gemessen 16.11.2026: 261,97 MB Spielordner -> 164,41 MB Paket). Das Vielfache gilt der Quelle, die ein Abbild
#: kleiner als das Spiel sein kann (``.ffpfsc``).
FORGE_PLATZ_FAKTOR = 1.2
#: Die Stufen, die Dump Forge meldet - fuer jede gibt es einen Text ``ps5pkg.forge_stage_<Stufe>``.
FORGE_STUFEN = ("extract", "scan", "preflight", "check", "plan", "compress", "write", "verify", "finalize")

_UNZULAESSIG = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
#: Ein Pfad im Spiel (``Media/a/b.bundle``) - ohne Klammern und Doppelpunkt, die eine Meldung des Werkzeugs traegt.
_PFADARTIG = re.compile(r"^[^()\[\]:]+$")


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
        ("source", t("ps5pkg.src_folder") if info.ist_ordner
         else t("ps5pkg.src_image", art=info.abbild) if info.ist_abbild
         else (t("ps5pkg.src_debug") if info.debug else (info.typ or "-"))),
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
                 *, master: "tk.Misc | None" = None, karte_bauer: "Callable | None" = None,
                 quelle_bauer: "Callable | None" = None) -> None:
        self.g = gui
        #: Von der Seite ``pkg_fpkg_seite``: baut die Karte (wie ``path_card`` der Aufgabe 1) und das Quellfeld darin.
        self._karte_bauer = karte_bauer
        self._quelle_bauer = quelle_bauer
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
                         "gelesen": [], "lesen_laeuft": 0, "scan": [], "bericht": [], "nachlauf": []}
        self._abbruch = False
        self._schliesst = False
        self._wandert = False                      # Schrittbalken im unbestimmten Modus (_balken_wandern)
        self._takt_id = None
        self._job: "dict | None" = None            # laufender Auftrag
        self._uebergabe: "dict | None" = None      # Hand-off an Aufgabe 1
        self._cover = None
        self._cover_ordner: list[str] = []
        self._staging: list[str] = []
        self._bau: dict = {}                       # Arbeitsordner und Vorher-Stand des laufenden Baus
        self._werkzeug_pfad = ""
        self._werkzeug_forge_pfad = ""
        self._befunde_gezeigt: "set[str]" = set()   # Quellen, deren Vorabbefunde schon im Protokoll stehen
        self.einbau = None                         # die Einbau-Karte der Seite (``_seite_umwandeln``)
        self._bericht_faden: "tuple | None" = None  # (Quelle, Faden) der laufenden Pruefung - ein Bau wartet darauf
        self._einbauten_gemeldet: "tuple | None" = None   # (Pfad, Stand) der Quelle, deren [Pruefung]-Zeilen schon im Protokoll stehen
        self._nachlauf = False                     # die Quelle wird gerade nach einem Erfolg geloescht (``_nach_erfolg``)
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

    def _werkzeug_forge(self) -> str:
        """Pfad zur Befehlszeile von Dump Forge (Ordner ``Dump-Forge-CLI``); ``""``, wenn es sie hier nicht gibt."""
        if not self._werkzeug_forge_pfad or not os.path.isfile(self._werkzeug_forge_pfad):
            self._werkzeug_forge_pfad = forge.werkzeug_suchen(self._wurzeln())
        return self._werkzeug_forge_pfad

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
    def _karte(self, eltern, titel_schluessel: str, polster=(16, 12), flach: bool = False):
        """Eine runde Karte mit Ueberschrift; die Kinder entstehen in der Karte selbst.

        ``pw.Karte`` statt ``_runde_seitenkarte``: Das Hauptprogramm hielte jede Karte seiner Seiten in einer Liste fest,
        ein geschlossenes Fenster liesse sie samt Bildern stehen (``test_fenster_leck``).

        ``flach``: statt der Karte ein schlichter Abschnitt wie bei den Aufgaben 1 bis 6 - ein Rahmen in der Farbe der
        Seite, darueber (wenn ``titel_schluessel`` gesetzt ist) die Beschriftung in Grossbuchstaben.
        """
        if flach:
            abschnitt = tk.Frame(eltern, bg=self.c["bg_main"])
            if titel_schluessel:
                tk.Label(abschnitt, text=self.t(titel_schluessel).upper(), font=(self.F, self.pt(9), "bold"),
                         bg=self.c["bg_main"], fg=self.c["fg_primary"], anchor="w").pack(fill="x", pady=(0, 5))
            return abschnitt
        karte = self.g._pw.Karte(eltern, bg=self.c["bg_card"], padx=polster[0], pady=polster[1])
        tk.Label(karte, text=self.t(titel_schluessel).upper(), font=(self.F, self.pt(9), "bold"),
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
        gespeichert = str(self._einstellung(EINST_FORMAT, opt.STANDARD_FORMAT))
        self.format_schluessel = gespeichert if gespeichert in [f[0] for f in FORMATE] else opt.STANDARD_FORMAT
        self.ueberschreiben_var = tk.BooleanVar(value=False)
        # Auf die PS5 entpacken: die Adresse ist die der Ansicht KONSOLE (ein Feld fuer alle Seiten), der Ordner gemerkt.
        self.adresse_var = g._konsole_ip_var()
        self.fern_var = tk.StringVar(value=str(self._einstellung(EINST_FERN, "/mnt/usb0") or "/mnt/usb0"))
        self._konsole_ansicht = False
        self._konsole_ziel = ("", "")              # (Adresse, Ordner) fuer den Arbeitsfaden - er liest keine Tk-Variable
        self.schritt_var = tk.StringVar(value="0 %")
        self.auftrag_var = tk.StringVar(value=t("ps5pkg.job_ready"))

        # Statuszeile und Knopfleiste unten (zuerst packen - sonst quetscht sie die Mindesthoehe weg)
        # Wie bei den Aufgaben 1 bis 6 (``status_label``, ``telemetry_label``): der Text rechts unten, kursiv, darunter klein, was
        # noch laeuft - hier das Lebenszeichen. Links steht nur der Zaehler der Quellen, und nur, wenn es mehrere sind.
        status = tk.Frame(self.win, bg=c["bg_main"], padx=14, pady=5)
        status.pack(side="bottom", fill="x")
        status.columnconfigure(1, weight=1)
        self.zaehler_var = tk.StringVar(value="")
        self.zaehler_label = tk.Label(status, textvariable=self.zaehler_var, font=(F, pt(9), "italic"), bg=c["bg_main"],
                                      fg=c["fg_secondary"], anchor="w")
        self.zaehler_label.grid(row=0, column=0, sticky="w")
        self.zaehler_label.grid_remove()            # erst bei mehreren Quellen (``_liste_fuellen``)
        self.status_label = tk.Label(status, textvariable=self.status_var, font=(F, pt(9), "italic"), bg=c["bg_main"],
                                     fg=c["fg_secondary"], anchor="e", justify="right")
        self.status_label.grid(row=0, column=1, sticky="e")
        status.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(200, e.width - 200)), add="+")
        self.lebt_var = tk.StringVar(value="")
        self.lebt_label = tk.Label(status, textvariable=self.lebt_var, font=(F, pt(8)), bg=c["bg_main"],
                                   fg=c["fg_secondary"], anchor="e", justify="right")
        self.lebt_label.grid(row=1, column=0, columnspan=2, sticky="e")
        self.lebt_label.grid_remove()               # ohne Lauf ganz aus dem Raster (wie ``telemetry_label``)
        rumpf = tk.Frame(self.win, bg=c["bg_main"])
        rumpf.pack(fill="both", expand=True)
        rumpf.columnconfigure(0, weight=1)
        rumpf.rowconfigure(2, weight=1)
        # Seit 30.10.2026 keine Reiterzeile mehr (``SICHTBARE_REITER``): Die Seite besteht wie die Aufgaben 1 bis 6 aus
        # einer Spalte; Quelle waehlt das Quellfeld der Seite ``pkg_fpkg_seite``.
        self._navigation(rumpf)
        if self._nav:
            tk.Frame(rumpf, height=1, bg=c["border"]).grid(row=1, column=0, sticky="ew", padx=14)
        flaeche = tk.Frame(rumpf, bg=c["bg_main"])
        flaeche.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 0))
        flaeche.columnconfigure(0, weight=1)
        flaeche.rowconfigure(0, weight=1)
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
        self._nav: dict[str, tuple[tk.Frame, tk.Label, tk.Label]] = {}
        if not SICHTBARE_REITER:
            return
        leiste = tk.Frame(eltern, bg=c["bg_main"])
        leiste.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 0))
        for schluessel, text in (("umwandeln", "ps5pkg.nav_convert"), ("bibliothek", "ps5pkg.nav_library"),
                                 ("extras", "ps5pkg.nav_extras"), ("optionen", "ps5pkg.nav_options")):
            if schluessel not in SICHTBARE_REITER:
                continue
            rahmen = tk.Frame(leiste, bg=c["bg_main"], cursor="hand2")
            rahmen.pack(side="left", padx=(0, 24))
            # Das Symbol der frueheren Leiste links entfaellt; das (leere, ungepackte) Label bleibt, damit ``_nav`` und
            # ``_seite_zeigen`` ihre Form behalten.
            symbol = tk.Label(rahmen, text="", bg=c["bg_main"], fg=c["fg_secondary"])
            name = tk.Label(rahmen, text=self.t(text), font=(F, pt(11)), bg=c["bg_main"], fg=c["fg_secondary"],
                            padx=2, pady=4)
            name.pack()
            strich = tk.Frame(rahmen, height=2, bg=c["bg_main"])
            strich.pack(fill="x")
            rahmen._strich = strich
            # "Optionen" ist keine Seite, sondern ein Dialog: Der Eintrag bleibt nie als gewaehlte Seite stehen.
            befehl = self._optionen_oeffnen if schluessel == "optionen" else (lambda s=schluessel: self._seite_zeigen(s))
            for w in (rahmen, name, strich):
                w.bind("<Button-1>", lambda _e, b=befehl: b())
            self._nav[schluessel] = (rahmen, symbol, name)

    def _seite_zeigen(self, schluessel: str) -> None:
        c = self.c
        self.seiten[schluessel].tkraise()
        for name, (rahmen, symbol, text) in self._nav.items():
            aktiv = name == schluessel
            text.configure(fg=c["fg_primary"] if aktiv else c["fg_secondary"])
            rahmen._strich.configure(bg=c["fg_accent"] if aktiv else c["bg_main"])
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
        # Seit 31.10.2026 (Nutzerwunsch) rollt die Seite nicht mehr: Sie steht in einem einfachen Rahmen, und das
        # Protokoll nimmt die uebrige Hoehe (es wird kuerzer, statt dass die Seite rollen muss).
        links = tk.Frame(seite, bg=c["bg_main"])
        links_aussen = links
        links_aussen.grid(row=0, column=0, sticky="nsew")
        links.columnconfigure(0, weight=1)
        links.rowconfigure(4, weight=1)
        # Seit 30.10.2026 eine einzige Spalte wie bei den Aufgaben 1 bis 6: Die Spalte rechts mit ERGEBNIS und Protokoll
        # ist weggefallen, beides steht unter AUFTRAG (``unten``) und rollt mit. ``spalte_rechts`` heisst weiter so
        # (Protokoll und Ergebnis liegen in ihr).
        rechts = tk.Frame(links, bg=c["bg_main"])
        rechts.grid(row=4, column=0, sticky="nsew", pady=(8, 4))
        self.spalte_rechts = rechts
        # Die Knopfleiste steht wie bei den Aufgaben 1 bis 6 unter den Abschnitten, das Protokoll darunter.
        self._leiste_bauen(links)

        # Die Karte wie ``path_card`` der Aufgabe 1 (getoent, runde Ecken): Quelle, Paket, Aktion, Ziel und Zielformat
        # stehen darin, Knopfleiste, Auftrag und Protokoll darunter auf dem Hauptbild. Ohne die Seite (``karte_bauer``
        # fehlt, z. B. im Test) stehen die Abschnitte lose in der Rollflaeche.
        if self._karte_bauer is not None:
            karte, konf = self._karte_bauer(links)
            karte.grid(row=0, column=0, sticky="ew")
            konf.columnconfigure(0, weight=1)
        else:
            konf = links
        basis = 0
        if self._quelle_bauer is not None:
            self._quelle_bauer(konf).grid(row=0, column=0, sticky="ew", pady=(0, 16))
            basis = 1

        # QUELLE: Die Wahl trifft das Quellfeld oben in der Karte (``pkg_fpkg_seite``, erkennt PS4/PS5 selbst); hier
        # steht das gewaehlte Paket mit seinen Angaben und darunter, was damit geschehen soll. Die Ablagezone und ihre
        # beiden Knoepfe werden weiter gebaut (Befehle und Ziele unveraendert), aber nicht angezeigt.
        quelle = self._karte(konf, "", flach=True)
        self.quelle_karte = quelle
        quelle.grid(row=basis + 1, column=0, sticky="ew", pady=(6, 0))
        oben = tk.Frame(quelle, bg=c["bg_main"])
        oben.columnconfigure(0, weight=1)
        self.ablage = tk.Canvas(oben, height=74, bg=c["bg_main"], highlightthickness=0, cursor="hand2")
        self.ablage.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.ablage.bind("<Configure>", self._ablage_malen)
        self.ablage.bind("<Button-1>", lambda _e: self._datei_waehlen())
        rechts_k = tk.Frame(oben, bg=c["bg_main"])
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

        # Das gewaehlte Paket steht fuer sich: kleine Ueberschrift, Titel, Pfad - und erst darunter, mit Abstand, die
        # Aktionen (Nutzer 11.10.2026: "viel zu nah beim Erstellen-Knopf, unuebersichtlich").
        self.paket_kopf = tk.Label(quelle, text=t("ps5pkg.selected_caption").upper(), font=(F, pt(9), "bold"),
                                   bg=c["bg_main"], fg=c["fg_primary"], anchor="w")
        # Seit 31.10.2026 nicht mehr angezeigt (Nutzerwunsch: "soll bitte weg aus der Anzeige"): Die Felder bleiben
        # bestehen und werden weiter gefuellt (Tests, Spielinfo), stehen aber nicht im Raster der Seite.
        self.paket_titel = tk.Label(quelle, text=t("ps5pkg.no_source"), font=(F, pt(13), "bold"),
                                    bg=c["bg_main"], fg=c["fg_primary"], anchor="w")
        zeile = tk.Frame(quelle, bg=c["bg_main"])
        self.paket_pfad = tk.Label(zeile, text="", font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"], anchor="w")
        self.paket_pfad.pack(side="left", fill="x", expand=True)
        self.paket_typ = tk.Label(zeile, text="", font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_accent"], padx=10)
        self.paket_typ.pack(side="right")
        self.paket_playgo = tk.Label(quelle, text="", font=(F, pt(9), "bold"), bg=c["bg_main"],
                                     fg=c.get("fg_warning", "#f0a32e"), anchor="w")
        self.paket_playgo.pack(fill="x")
        # Die Aktionen (Umwandeln, Extrahieren, Pruefen, Auf die PS5 entpacken) stehen seit 31.10.2026 im Auswahlfeld
        # ZIELFORMAT (``format_box``); die Aktionsvariable und alles, was von ihr abhaengt, ist unveraendert. Die Zeilen
        # Zielordner / Konsole haengen sich hinter das Paket (``aktion_reihe``).
        self.aktion_reihe = self.paket_playgo
        ziel = tk.Frame(quelle, bg=c["bg_main"])
        ziel.pack(fill="x", pady=(8, 0))
        self.ziel_reihe = ziel
        ziel.columnconfigure(1, weight=1)
        # Wie die Zielordner-Zeile der Aufgaben 1 bis 6: die Beschriftung in Grossbuchstaben darueber, Feld und Knopf darunter.
        tk.Label(ziel, text=t("ps5pkg.target_folder").upper(), font=(F, pt(9), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
        self.ziel_feld = pw.Entry(ziel, textvariable=self.ziel_var, font=(F, pt(12)), bg=c["bg_main"],
                                  fg=c["fg_primary"], insertbackground=c["fg_primary"], relief="flat")
        self.ziel_feld.grid(row=1, column=0, columnspan=2, sticky="ew", ipady=3)
        pw.Button(ziel, text=g._t("main.choose_folder_button"), command=self._ziel_waehlen, hoehe=36, fett=True).grid(
            row=1, column=2, padx=(8, 0))
        self._nach_erfolg_haken_bauen(quelle)       # baut auch "Vorhandenes ueberschreiben": alle fuenf Haken teilen sich ein Raster
        # Auf die PS5 entpacken: statt des Zielordners auf dem PC die Adresse und der Ordner auf der Konsole. Erst
        # sichtbar, wenn diese Aktion gewaehlt ist (:meth:`_aktion_anwenden`).
        fern = tk.Frame(quelle, bg=c["bg_main"])
        self.fern_reihe = fern
        fern.columnconfigure(1, weight=1)
        optionen = dict(font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_primary"], insertbackground=c["fg_primary"],
                        relief="flat")
        tk.Label(fern, text=t("ps5pkg.console_address"), font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_secondary"]).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.adresse_feld = pw.Entry(fern, textvariable=self.adresse_var, **optionen)
        self.adresse_feld.grid(row=0, column=1, sticky="ew", ipady=3)
        tk.Label(fern, text=t("ps5pkg.console_folder"), font=(F, pt(10)), bg=c["bg_main"], fg=c["fg_secondary"]).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(6, 0))
        self.fern_feld = pw.Entry(fern, textvariable=self.fern_var, **optionen)
        self.fern_feld.grid(row=1, column=1, sticky="ew", ipady=3, pady=(6, 0))
        self.fern_feld.bind("<KeyRelease>", lambda _e: self._ergebnis_fuellen(), add="+")
        hinweis = tk.Label(fern, text=t("ps5pkg.console_hint"), font=(F, pt(9)), bg=c["bg_main"], fg=c["fg_secondary"],
                           anchor="w", justify="left", wraplength=520)
        hinweis.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        # Der Umbruch folgt der Breite der Zeile (das Label selbst hat auf dem Hauptbild die Groesse seines Textes).
        fern.bind("<Configure>", lambda e: hinweis.configure(wraplength=max(120, e.width - 6)), add="+")

        # ZIELFORMAT
        formate = self._karte(konf, "", flach=True)
        formate.grid(row=basis, column=0, sticky="ew")
        # Wie die Karte der Aufgaben 1 bis 6 (Nutzerwunsch 17.11.2026: "so aussieht wie bei Aufgabe 1 bis 6"): ZIELFORMAT ->
        # KOMPRESSION (PFS) -> WORKER -> PRUEFUNG in einer Zeile mit Pfeilen, darunter der Hinweis, rechts daneben BEIM
        # ERSTELLEN EINBAUEN (AMPR EMU, PlayGo, DLC EMU, BACKPORT) - mit denselben Variablen und Befehlen wie dort
        # (``pkg_einbau_karte``). Der Lauf, der aus diesem Fenster an Aufgabe 1 geht, liest genau diese Felder.
        self.einbau = einbau_ui.EinbauKarte(self, formate)
        self.einbau.rahmen.pack(fill="x", anchor="w")
        format_titel = tk.Label(self.einbau.reihe, text=t("ps5pkg.card_format").upper(), font=(F, pt(9), "bold"),
                                bg=c["bg_main"], fg=c["fg_primary"], anchor="w")
        # Seit 31.10.2026 (Nutzerwunsch) ein Auswahlfeld wie ZIELFORMAT bei Aufgabe 1 (direkt unter QUELLE) statt fuenf
        # Kacheln und der Aktionszeile: die fuenf Formate ("Umwandeln zu ...") und die Aktionen Extrahieren, Pruefen und
        # Auf die PS5 entpacken. Wirkung wie zuvor: ``_format_waehlen`` und ``_aktion_geaendert``.
        self.format_var = tk.StringVar(value="")
        self.format_box = pw.Combobox(self.einbau.reihe, textvariable=self.format_var, state="readonly", width=16, kompakt=True,
                                      values=tuple(e[2] for e in self._format_eintraege()), font=(F, pt(10)))
        self.format_box.bind("<<ComboboxSelected>>", self._format_gewaehlt)
        self._format_anzeigen()
        self.einbau.kopf_bauen(format_titel, self.format_box)
        self._bauform_reihe_bauen(formate)

        # Der Auftrag steht wie bei den Aufgaben 1 bis 6 in der Aktionsleiste (``_leiste_bauen``): ein Balken mit Prozentzahl, rechts
        # daneben der Text. Die Werte des Schrittbalkens (``balken``) und des Gesamtbalkens (``balken_gesamt``) laufen weiter - der
        # Schrittbalken ist nicht zu sehen, die Leiste zeigt den Gesamtstand.
        auftrag = None
        self.datei_var = tk.StringVar(value="")

        # ERGEBNIS (Ausgabe, Titel-ID, Inhalt, Groesse, Freier Platz): Die Chips sind seit 31.10.2026 nicht mehr zu sehen
        # (Nutzerwunsch); die Werte werden weiter gefuellt (``_ergebnis_fuellen``), die Anzeige entfaellt.
        self.ergebnis_var = {schluessel: tk.StringVar(value="") for schluessel in
                             ("output", "title_id", "content", "size", "free")}
        # Das Cover steht seit dem 13.10.2026 (Nutzerwunsch) nicht mehr hier, sondern wie bei den Aufgaben 1 bis 6 in der
        # Seitenleiste (:meth:`_spielinfo_zeigen`); der Knopf "Vorschau oeffnen" ist entfallen.
        # Das Protokoll liegt unter dem Auftrag: In der Karte AUFTRAG blieb ihm bei normaler Fensterhoehe keine Hoehe -
        # der Text war nicht zu sehen. Es hat eine feste Hoehe (die Seite rollt); die Breite bestimmt die Spalte
        # (width=1), nicht der Text.
        self.protokoll = pw.Text(rechts, height=3, width=1, font=(self.M, pt(10)), bg=c["console_bg"],
                                 fg=c["console_fg"], relief="flat", wrap="word", state="disabled")
        self.protokoll.pack(fill="both", expand=True, pady=(4, 0))
        self._protokoll_menue_einrichten()
        # Seit 17.11.2026 ohne Abstand nach jeder Meldung (frueher 14.10.2026 mit): Das Protokoll sieht aus wie bei den Aufgaben 1
        # bis 6 - Schrift 10 pt, Zeile an Zeile.
        # Alles unter dem Quellfeld: Zielformat, Paket, Knopfleiste, Auftrag, Protokoll (siehe ``rest_zeigen``).
        self._rest = (formate, quelle, self.leiste, rechts)
        self._rest_sichtbar = True

    def rest_zeigen(self, sichtbar: bool) -> bool:
        """Blendet alles unter dem Quellfeld ein oder aus (31.10.2026: Die Seite zeigt vor der ersten gueltigen Wahl nur QUELLE).

        Die Abschnitte bleiben gebaut und werden nur aus dem Raster genommen - ihre Werte, Befehle und das Protokoll
        arbeiten weiter. Liefert ``True``, wenn sich etwas geaendert hat.
        """
        if sichtbar == self._rest_sichtbar:
            return False
        for teil in self._rest:
            try:
                teil.grid() if sichtbar else teil.grid_remove()
            except tk.TclError:
                pass
        self._rest_sichtbar = sichtbar
        return True

    def _leiste_bauen(self, eltern) -> None:
        """Die Aktionsleiste wie bei den Aufgaben 1 bis 6 (``action_bar``): STARTEN, ABBRECHEN, dann - nur waehrend eines Laufs - der
        Fortschrittsbalken mit der Prozentzahl, und rechts daneben der Text (im Leerlauf die Groesse der Quelle, im Lauf die
        Dateizeile des Werkzeugs).

        Nutzerwunsch 17.11.2026: Fortschrittsbalken, Prozentzahl und Text sollen aussehen wie bei den anderen Aufgaben. "Updates
        Online", "Dateien anzeigen", "Details" und "Optionen" liegen im Rechtsklick-Menue des Protokolls
        (``_protokoll_menue_einrichten``). Die Leiste steht unter dem Abschnitt Quelle/Zielformat (Zeile 2 der Rollflaeche), darunter
        das Protokoll.
        """
        c, F, pt = self.c, self.F, self.pt
        leiste = tk.Frame(eltern, bg=c["bg_main"])
        leiste.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        # Wie ``action_bar`` des Hauptfensters: der Balken ist die einzige dehnbare Spalte und gibt den Platz her, den Prozentzahl
        # und Text rechts davon brauchen.
        leiste.columnconfigure(2, weight=1, minsize=200)
        leiste.columnconfigure(3, weight=0, minsize=56)
        self.leiste = leiste
        # STARTEN und ABBRECHEN wie bei Aufgabe 1 (``run_btn``/``abort_btn``): derselbe Text, dieselbe Groesse.
        haupt = hauptknoepfe.starten_abbrechen(self.g, leiste, self.g._t("action.start"), self._starten, self._abbrechen)
        if haupt is not None:
            self.start_knopf, self.abbrechen_knopf = haupt
        else:
            self.start_knopf = self._pille(leiste, "action.start", self._starten, akzent=True)
            self.abbrechen_knopf = self._pille(leiste, "action.cancel", self._abbrechen)
        self.start_knopf.grid(row=0, column=0, padx=(0, 12))
        self.abbrechen_knopf.grid(row=0, column=1, padx=(0, 24))
        self.abbrechen_knopf.configure(state="disabled")
        pw = self.g._pw
        # Der Schrittbalken ist nicht zu sehen (kein Elternfenster im Raster), laeuft aber mit - Tests und Anzeige-Logik lesen ihn.
        self._balken_versteck = tk.Frame(self.win)
        self.balken = pw.Progressbar(self._balken_versteck, mode="determinate", maximum=100.0)
        self.balken_gesamt = pw.Progressbar(leiste, mode="determinate", maximum=100.0)
        self.balken_gesamt.grid(row=0, column=2, sticky="ew", ipady=5)
        self.prozent_var = tk.StringVar(value="0 %")
        self.prozent_label = tk.Label(leiste, textvariable=self.prozent_var, width=5, anchor="e", font=(F, pt(11), "bold"),
                                      bg=c["bg_main"], fg=c["fg_accent"])
        self.prozent_label.grid(row=0, column=3, padx=(15, 0), sticky="e")
        self.groesse_var = tk.StringVar(value="")
        self.groesse_label = tk.Label(leiste, textvariable=self.groesse_var, font=(F, pt(9), "bold"), bg=c["bg_main"],
                                      fg=c["fg_primary"], anchor="w", justify="left", wraplength=520)
        self.groesse_label.grid(row=0, column=4, padx=(15, 0), sticky="w")
        self._fortschritt_sichtbar = True
        self._fortschritt_zeigen(False)             # im Leerlauf unsichtbar, wie ``progress`` und ``percent_label``

    def _fortschritt_zeigen(self, an: bool) -> None:
        """Balken und Prozentzahl nur waehrend eines Laufs (``_launch_task`` / Ende dort); der Text daneben bleibt."""
        if an == self._fortschritt_sichtbar:
            return
        self._fortschritt_sichtbar = an
        for teil in (self.balken_gesamt, self.prozent_label):
            try:
                teil.grid() if an else teil.grid_remove()
            except tk.TclError:
                pass

    def _groesse_text(self) -> str:
        """Der Text rechts neben dem Balken: im Lauf die Dateizeile (was gerade entsteht), sonst die Groesse der Quelle."""
        if self._job is not None:
            return self.datei_var.get()
        info = self.aktuell
        if info is None or not info.groesse:
            return ""
        try:
            return self._fmt(int(info.groesse))
        except (TypeError, ValueError):
            return ""

    def _aktion_moeglich(self, aktion: str) -> bool:
        """Ein Spielordner oder Abbild kennt nur Erstellen / Umwandeln - entpacken und pruefen gibt es nur fuer Pakete."""
        info = self.aktuell
        return info is None or not info.ist_quelle or aktion == AKTION_UMWANDELN

    def _format_moeglich(self, schluessel: str) -> bool:
        """Das Format Paket (Bau eines Debug-Pakets) gibt es fuer einen Spielordner und ein Abbild.

        Aus einem Abbild geht hier nur das Paket: ``.ffpkg``, ``.ffpfsc``, ``.ffpfs`` und ``.exFAT`` baut das Hauptprogramm
        (Aufgaben 1 bis 6), nicht dieser Bereich.
        """
        info = self.aktuell
        if info is None:
            return True
        if info.ist_abbild:
            return schluessel == FORMAT_PAKET
        return schluessel != FORMAT_PAKET or info.ist_ordner

    def _format_eintraege(self) -> "list[tuple[str, str, str]]":
        """Die Eintraege des Auswahlfelds als (Art, Schluessel, Text): erst die Formate, dann die uebrigen Aktionen."""
        t = self.t
        # Seit 01.11.2026 nur die Endung (Nutzerwunsch: ".ffpkg", ".ffpfsc", ".ffpfs", ".exFAT", ".pkg" ohne "Umwandeln zu").
        liste = [("format", schluessel, ".exFAT" if schluessel == "exfat" else endung)
                 for schluessel, _name, endung in FORMATE]
        liste += [("aktion", AKTION_EXTRAHIEREN, t("ps5pkg.action_extract")),
                  ("aktion", AKTION_PRUEFEN, t("ps5pkg.action_check")),
                  ("aktion", AKTION_KONSOLE, t("ps5pkg.action_console"))]
        return liste

    def _format_anzeigen(self) -> None:
        """Zeigt Format beziehungsweise Aktion im Auswahlfeld (nach Wahl, Optionen, Aktionswechsel, beim Start)."""
        aktion = self.aktion_var.get()
        text = ""
        for art, schluessel, eintrag in self._format_eintraege():
            if (art == "aktion" and schluessel == aktion) or (
                    art == "format" and aktion == AKTION_UMWANDELN and schluessel == self.format_schluessel):
                text = eintrag
                break
        if self.format_var.get() != text:
            self.format_var.set(text)

    def _format_gewaehlt(self, _e=None) -> None:
        wahl = self.format_var.get()
        for art, schluessel, eintrag in self._format_eintraege():
            if eintrag != wahl:
                continue
            if art == "format":
                self._format_waehlen(schluessel)
            elif not self._aktion_moeglich(schluessel):
                self._status(self.t("ps5pkg.action_only_package"))
                self._format_anzeigen()                  # das Feld springt auf die bisherige Wahl zurueck
            else:
                self.aktion_var.set(schluessel)
                self._aktion_geaendert()
            return
        self._format_anzeigen()

    def _format_waehlen(self, schluessel: str) -> None:
        if not self._format_moeglich(schluessel):
            self._status(self.t("ps5pkg.format_only_package" if self.aktuell is not None and self.aktuell.ist_abbild
                                else "ps5pkg.format_only_folder"))
            self._format_anzeigen()                  # das Feld springt auf das bisherige Format zurueck
            return
        if self.aktion_var.get() != AKTION_UMWANDELN:
            self.aktion_var.set(AKTION_UMWANDELN)
            self._aktion_geaendert()
        self.format_schluessel = schluessel
        self._merken(EINST_FORMAT, schluessel)
        self._format_anzeigen()
        self._ergebnis_fuellen()
        if schluessel in FORMATE_MIT_RUCKELHINWEIS:
            # Wie im Hauptfenster (``_format_hinweis_setzen``): das Tempo der Entpackung und die Empfehlung, ein Satz.
            self._status(self.t("main.pfs_speed_hint"))

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
    def _seite_extras(self, seite, mit_kopf: bool = True) -> None:
        """Die vier Werkzeug-Karten. ``mit_kopf=False``: ohne Ueberschrift (das eigene Fenster unter WEITERE TOOLS
        hat schon eine, siehe :mod:`ps5_validator.ui.pkg_extras_fenster`)."""
        g, t, c = self.g, self.t, self.c
        F, pt = self.F, self.pt
        pw = g._pw
        seite.columnconfigure(0, weight=1)
        seite.rowconfigure(1, weight=1)
        if mit_kopf:
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

    @staticmethod
    def _ist_quelldatei(name: str) -> bool:
        """Ein ``.pkg`` oder ein Abbild (``.ffpkg``, ``.ffpfsc``, ``.ffpfs``, ``.exfat``) - was die Bibliothek aufnimmt."""
        klein = name.lower()
        return klein.endswith(".pkg") or bool(forge.abbild_art(klein))

    def _pkg_in(self, ordner: str) -> list[str]:
        """Die ``.pkg`` und Abbilder in einem Ordner - eine Ebene tief (Spiele liegen oft in je einem Unterordner)."""
        gefunden: list[str] = []
        try:
            for eintrag in sorted(os.scandir(ordner), key=lambda e: e.name.lower()):
                if eintrag.is_file() and self._ist_quelldatei(eintrag.name):
                    gefunden.append(eintrag.path)
                elif eintrag.is_dir():
                    try:
                        for tiefer in sorted(os.scandir(eintrag.path), key=lambda e: e.name.lower()):
                            if tiefer.is_file() and self._ist_quelldatei(tiefer.name):
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
        alle: list[str] = []
        for p in pfade:
            if os.path.isdir(p):
                alle.extend(self._quellen_in(p))
            elif os.path.isfile(p) and self._ist_quelldatei(p):
                alle.append(p)
        # Ein Abbild liest Dump Forge, alles andere ffpfsc-pkg-tool: Es fehlt nur das Werkzeug, das die Quelle braucht.
        if (not alle or any(not forge.abbild_art(p) for p in alle)) and not self._werkzeug():
            self._fehler(self.t("ps5pkg.err_no_tool"))
            return
        if any(forge.abbild_art(p) for p in alle) and not self._werkzeug_forge():
            self._fehler(self.t("ps5pkg.err_no_tool_forge"))
            return
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
        forge_exe = self._werkzeug_forge()
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
                    elif forge.abbild_art(pfad):
                        info = forge.lesen(forge_exe, pfad, arbeit, popen_extra=popen_extra)
                    else:
                        info = wz.lesen(werkzeug, pfad, arbeit, passcode=self._passcode(), popen_extra=popen_extra)
                    fertig.append(info)
                except Exception as exc:  # noqa: BLE001
                    if not isinstance(exc, wz.Fehler):
                        logger.exception("Paket lesen")
                    text = self.t("ps5pkg.log_read_failed", name=os.path.basename(pfad), grund=str(exc))
                    self._melden(text)
                    with self._sperre:
                        self._z["lesefehler"] = text
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
        self._status(self._lese_status())

    def _lese_status(self) -> str:
        """Die Statuszeile nach dem Lesen: "Bereit." - oder warum das zuletzt gewaehlte Paket nicht lesbar war.

        Bis zum 03.11.2026 stand nach einem unlesbaren Paket nur "Bereit." da, und STARTEN blieb ohne Erklaerung grau.
        """
        if self._job is not None:
            return str(self.status_var.get())
        with self._sperre:
            fehler, self._z["lesefehler"] = self._z.get("lesefehler", ""), ""
        return fehler or self.t("ps5pkg.status_idle")

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
        if neu and (self._werkzeug() or self._werkzeug_forge()):
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
                self._format_anzeigen()
        if self.aktuell is not None:
            self._cover_zeigen(self.aktuell)
            self._spielinfo_zeigen(self.aktuell)
        self._liste_fuellen(auswaehlen=self.aktuell.pfad if self.aktuell is not None else "")
        self._knoepfe_pruefen()
        if werte[opt.ORDNER] and (werte[opt.ORDNER] != alt[opt.ORDNER] or werte[opt.REKURSIV] != alt[opt.REKURSIV]):
            self._ordner_scan_starten(werte[opt.ORDNER], werte[opt.REKURSIV])
        if neue_quellen and (self._werkzeug() or self._werkzeug_forge()):
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
        try:
            self.zaehler_label.grid() if len(self.pakete) > 1 else self.zaehler_label.grid_remove()
        except tk.TclError:
            pass
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
        if self._job is None and self._uebergabe is None:
            self._anzeige_zuruecksetzen()
        self.paket_titel.configure(text="%s — %s" % (info.title_id, info.titel) if info.title_id and info.titel
                                   else (info.titel or os.path.basename(info.pfad)))
        self.paket_pfad.configure(text="%s · %s" % (info.pfad, self._fmt(info.groesse)))
        self.paket_typ.configure(text=self.t("ps5pkg.badge_folder") if info.ist_ordner
                                 else self.t("ps5pkg.badge_image", art=info.abbild.upper()) if info.ist_abbild
                                 else self.t("ps5pkg.badge_debug") if info.debug else (info.typ or ""))
        # PlayGo-Hinweis: Ordner direkt, Archive im Hintergrund (Subprocess).
        if info.ist_ordner:
            merkmal = wz.playgo_erklaert_ordner(info.pfad)
            self.paket_playgo.configure(
                text=self.t("pkg.playgo_hinweis", datei=merkmal) if merkmal else "")
        else:
            self.paket_playgo.configure(text="")
            ext = os.path.splitext(info.pfad)[1].lower()
            # Ein Abbild liest ffpfsc-pkg-tool nicht (es ist kein Paket): Der PlayGo-Hinweis steht beim Lesen in Forges Befunden.
            if ext in (".pkg", ".ffpfsc", ".ffpfs", ".exfat", ".ffpkg") and not info.ist_abbild:
                pfad_snap = info.pfad
                def _pruefe_archiv_playgo(p=pfad_snap):
                    merkmal = wz.playgo_erklaert_archiv(p, self._werkzeug(), self._wurzeln())
                    def _ui():
                        if hasattr(self, "paket_playgo") and self.aktuell and self.aktuell.pfad == p:
                            self.paket_playgo.configure(
                                text=self.t("pkg.playgo_hinweis", datei=merkmal) if merkmal else "")
                    # Die Seite hat kein eigenes ``after`` (``self.after`` warf hier AttributeError, still verschluckt:
                    # der PlayGo-Hinweis eines Pakets erschien nie) - der Fensterfaden uebernimmt.
                    self.g._hauptfaden_planen(_ui)
                import threading as _threading
                _threading.Thread(target=_pruefe_archiv_playgo, daemon=True).start()
        # Was fuer diese Quelle nicht geht, springt auf den Vorgabewert zurueck (ohne es zu speichern).
        if not self._aktion_moeglich(self.aktion_var.get()):
            self.aktion_var.set(AKTION_UMWANDELN)
        if not self._format_moeglich(self.format_schluessel):
            self.format_schluessel = FORMAT_PAKET if info.ist_abbild else "ffpfsc"
        self._aktion_anwenden()
        # Forges Vorabbefunde zur Quelle (Fehler und Warnungen): einmal je Quelle ins Protokoll, nicht stumm.
        if info.befunde and info.pfad not in self._befunde_gezeigt:
            self._befunde_gezeigt.add(info.pfad)
            for befund in info.befunde[:20]:
                self._protokoll("[Dump Forge] %s" % befund)
        self._cover_zeigen(info)
        self._spielinfo_zeigen(info)
        self._bericht_aktualisieren()            # die [Pruefung]-Zeilen der Aufgaben 1 bis 6 ins Protokoll (eingebaut? PlayGo noetig?)
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
                               else self.t("ps5pkg.badge_image", art=info.abbild.upper()) if info.ist_abbild
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

    @staticmethod
    def _forge_dateiname(info: "wz.PaketInfo") -> str:
        """``Titel [PPSA00000].pkg`` - der Name des Pakets, das Dump Forge aus dieser Quelle baut (63 Bytes ohne Endung)."""
        name = os.path.basename(os.path.normpath(info.pfad))
        titel = sauberer_name(info.titel) or sauberer_name(name if info.ist_ordner else os.path.splitext(name)[0])
        kennung = info.title_id if info.title_id and info.title_id not in titel else ""
        return forge.dateiname_fuer(titel, kennung)

    def _ziel_name(self) -> str:
        """Name des Ergebnisses: Ordner oder Datei mit Endung."""
        if self.aktuell is None:
            return ""
        name = anzeigename(self.aktuell)
        if self.aktuell.ist_ordner:
            # Aufgabe 1 benennt das Ergebnis nach dem Ordner selbst (gemessen 03.11.2026: "PPSA19015 Arcade Game
            # Zone.exfat", im Protokoll stand der Anzeigename mit der Title-ID in Klammern).
            name = os.path.basename(os.path.normpath(self.aktuell.pfad)) or name
        if self.aktion_var.get() == AKTION_UMWANDELN:
            if self.format_schluessel == FORMAT_PAKET:
                return self._forge_dateiname(self.aktuell)                 # den Namen legt das Programm fest
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
                self.fern_reihe.pack(fill="x", pady=(10, 0), after=self.aktion_reihe)
            else:
                self.fern_reihe.pack_forget()
                self.ziel_reihe.pack(fill="x", pady=(10, 0), after=self.aktion_reihe)
            # "Vorhandenes ueberschreiben" gehoert zum Zielordner auf dem PC; die uebrigen Haken ruecken zusammen.
            self._ueberschreiben_zeigen = not konsole
            # Noch nicht angezeigt (Breite 1): eine Spalte; das erste <Configure> beim Anzeigen verteilt sie auf die wirkliche Breite.
            self._haken_anordnen(int(self.nach_erfolg_rahmen.winfo_width()))
        except tk.TclError as exc:
            logger.debug("Zeilen der Aktion nicht umschaltbar: %s", exc)

    def _aktion_anwenden(self) -> None:
        """Zielformat, Ergebnis und Knoepfe zur Aktion nachziehen - ohne zu speichern (auch beim Oeffnen)."""
        self._konsole_zeilen_zeigen()
        self._format_anzeigen()
        self._ergebnis_fuellen()
        self._knoepfe_pruefen()

    def _knoepfe_pruefen(self) -> None:
        laeuft = self._job is not None or self._uebergabe is not None
        # Datei-Browser nur fuer .pkg-Dateien (list-inner braucht ein Paket, keinen Ordner)
        browser_ok = (self.aktuell is not None and not self.aktuell.ist_quelle
                      and bool(self._werkzeug()))
        # Detail-Fenster nur fuer Spielordner
        detail_ok = self.aktuell is not None and bool(self.aktuell.ist_ordner)
        # Updates Online nur fuer PS5-Spielpakete (PPSA/PPSS)
        update_ok = (self.aktuell is not None and bool(self.aktuell.title_id)
                     and self.aktuell.title_id.upper().startswith(("PPSA", "PPSS")))
        try:
            self.start_knopf.configure(state="disabled" if (laeuft or self.aktuell is None) else "normal")
            self.abbrechen_knopf.configure(state="normal" if laeuft else "disabled")
            self.cover_knopf.configure(state="normal" if self.aktuell is not None else "disabled")
        except tk.TclError:
            pass
        # Die vier Zusatzfunktionen stehen im Rechtsklick-Menue des Protokolls: gesperrt, wo sie nichts bewirken.
        for name, frei in (("update", update_ok), ("browser", browser_ok), ("detail", detail_ok)):
            try:
                self.protokoll_menue.entryconfigure(self._menue_eintraege[name], state="normal" if frei else "disabled")
            except (tk.TclError, KeyError, AttributeError):
                pass

    def _fehler(self, text: str) -> None:
        self._protokoll(text)
        messagebox.showerror(self.t("ps5pkg.window_title"), text, parent=self.win)

    def _balken_wandern(self, an: bool) -> None:
        """Der Schrittbalken wandert, solange die Dauer unbekannt ist (Pruefen) - sonst zeigt er den Prozentwert."""
        if an == self._wandert:
            return
        self._wandert = an
        try:
            if an:
                for balken in (self.balken, self.balken_gesamt):
                    balken.configure(mode="indeterminate")
                    balken.start()
                self.schritt_var.set("…")
                self.prozent_var.set("…")
            else:
                for balken in (self.balken, self.balken_gesamt):
                    balken.stop()
                    balken.configure(mode="determinate")
        except tk.TclError:
            pass

    def _anzeige_setzen(self, schritt: float, gesamt: float) -> None:
        """Beide Balken und die Prozentzahl daneben - immer zusammen, damit Zahl und Balken nie auseinanderlaufen."""
        self._balken_wandern(False)
        self.balken["value"] = schritt
        self.balken_gesamt["value"] = gesamt
        self.schritt_var.set("%d %%" % int(schritt))
        self.prozent_var.set("%d %%" % int(gesamt))

    def _anzeige_zuruecksetzen(self) -> None:
        """Ein neu gewaehltes Paket beginnt bei 0: Balken, Zahl, Auftrag und Dateizeile des vorigen Laufs verschwinden.

        Gemeldet am 03.11.2026: Nach einem Lauf blieben beide Balken auf 100 % - wer danach ein anderes Spiel in die
        Quelle lud, sah "100 %", obwohl noch nichts geschehen war.
        """
        self._anzeige_setzen(0, 0)
        try:
            self.auftrag_var.set(self.t("ps5pkg.job_ready"))
            self.datei_var.set("")
        except tk.TclError:
            pass

    def beschaeftigt(self) -> bool:
        """Laeuft gerade ein Auftrag, die Umwandlung in Aufgabe 1 oder das Loeschen der Quelle danach?"""
        return self._job is not None or self._uebergabe is not None or self._nachlauf

    def programmende(self, warten: float = 30.0) -> None:
        """Beim Beenden des Programms (aus dem Abbau-Faden): abbrechen, Werkzeuge beenden, Arbeitsordner wegraeumen.

        Bis zum 03.11.2026 setzte nur die Zerstoerung des Fensters den Abbruch - der Arbeitsfaden hing in ``read`` und
        starb mit dem Programm, das Werkzeug lief weiter und hielt die Dateien im Ziel offen.
        """
        self._abbruch = True
        ende = time.monotonic() + max(0.0, warten)
        wz.alle_beenden()
        while self._job is not None and time.monotonic() < ende:
            with self._sperre:
                if self._z.get("fertig") is not None:
                    break
            time.sleep(0.1)
        wz.alle_beenden()
        job = self._job or {}
        if job.get("art") == "extrahieren":
            self._teilergebnis_wegraeumen(job.get("ziel", ""))
        if job.get("art") == "bauen":
            self._unfertiges_wegraeumen(job.get("ziel", ""), getattr(self, "_bau", {}) or {})
        self._staging_raeumen()

    def _teilergebnis_wegraeumen(self, ordner: str) -> None:
        """Ein abgebrochenes oder gescheitertes Entpacken hinterlaesst einen halben Spielordner - er ist unbrauchbar.

        Der Ordner ist immer einer dieses Laufs: Ein vorhandener, nicht leerer wird vor dem Start nur mit dem Haken
        "Ueberschreiben" angenommen und dann geleert (``_starten``).
        """
        if not ordner or not os.path.isdir(ordner):
            return
        try:
            _haupt(self.g)._rmtree_force(ordner, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Halber Spielordner %s nicht entfernbar: %s", ordner, exc)
        if os.path.isdir(ordner):
            self._protokoll(self.t("ps5pkg.err_cannot_clear", pfad=ordner))

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

    def _updates_online(self) -> None:
        """Oeffnet die Spielinfo-Box mit den PS5-Updates fuer das gewaehlte Paket."""
        info = self.aktuell
        if info is None or not info.title_id:
            self._status(self.t("ps5pkg.kein_ps5_spiel"))
            return
        tid = info.title_id.upper()
        if not tid.startswith(("PPSA", "PPSS")):
            self._status(self.t("ps5pkg.kein_ps5_spiel"))
            return
        g = self.g
        g._letzte_meta = {
            "title_id": tid,
            "version_file_uri": str(info.param.get("versionFileUri", "") or ""),
        }
        g._cached_title_id = tid
        g._show_info_box()

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

    def _protokoll_menue_einrichten(self) -> None:
        """Rechtsklick im Protokoll: Kopieren, Alles waehlen - und "Ausgabe oeffnen" / "Verlauf leeren" (31.10.2026).

        Die beiden Knoepfe unter dem Auftrag sind entfallen; ihre Funktionen liegen hier. Das Menue ersetzt auf dem
        Protokoll das allgemeine Bearbeiten-Menue des Programms (nur Kopieren und Alles waehlen waren dort nutzbar).
        """
        c, t = self.c, self.t
        menue = tk.Menu(self.protokoll, tearoff=0, bg=c["bg_card"], fg=c["fg_primary"], activebackground=c["fg_accent"],
                        activeforeground=c["bg_main"], font=(self.F, self.pt(10)))
        menue.add_command(label=self.g._t("context.copy"), command=lambda: self.protokoll.event_generate("<<Copy>>"))
        menue.add_command(label=self.g._t("context.select_all"),
                          command=lambda: self.protokoll.tag_add("sel", "1.0", "end-1c"))
        menue.add_separator()
        menue.add_command(label=t("ps5pkg.open_output"), command=self._ausgabe_oeffnen)
        menue.add_command(label=t("ps5pkg.clear_log"), command=self._verlauf_leeren)
        # Seit 17.11.2026 hier statt als Knoepfe in der Leiste (sie soll aussehen wie bei den Aufgaben 1 bis 6).
        menue.add_separator()
        self._menue_eintraege: "dict[str, int]" = {}
        for name, schluessel, befehl in (("update", "ps5pkg.btn_update", self._updates_online),
                                         ("browser", "ps5pkg.browser_button", self._browser_oeffnen),
                                         ("detail", "ps5pkg.detail_button", self._detail_oeffnen),
                                         ("optionen", "ps5pkg.nav_options", self._optionen_oeffnen)):
            menue.add_command(label=t(schluessel), command=befehl)
            self._menue_eintraege[name] = menue.index("end")
        self.protokoll_menue = menue

        def zeigen(ereignis) -> str:
            try:
                menue.tk_popup(ereignis.x_root, ereignis.y_root)
            finally:
                menue.grab_release()
            return "break"

        for taste in ("<Button-3>", "<Button-2>") if sys.platform == "darwin" else ("<Button-3>",):
            self.protokoll.bind(taste, zeigen)

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
        aktion = self.aktion_var.get()
        # Den Bau eines Pakets aus einem Abbild oder Spielordner macht Dump Forge, seit 17.11.2026 als einziger Paketersteller
        # (LibProsperoPkg und ProsperoPkgTool bauen nicht mehr): Es braucht weder ffpfsc-pkg-tool noch die .NET-Laufzeit.
        # Ein ``.pkg`` schreibt Dump Forge im Strom in ein Abbild (Nutzerwunsch 17.11.2026, kein Zwischenordner): auch dafuer
        # braucht es weder ffpfsc-pkg-tool noch die .NET-Laufzeit.
        direkt = aktion == AKTION_UMWANDELN and not info.ist_quelle and self._abbild_direkt_moeglich(info)
        forge_weg = direkt or (info.ist_quelle and aktion == AKTION_UMWANDELN and self.format_schluessel == FORMAT_PAKET)
        if forge_weg:
            if not self._werkzeug_forge():
                self._fehler(self.t("ps5pkg.err_no_tool_forge"))
                return
        else:
            werkzeug = self._werkzeug()
            if not werkzeug:
                self._fehler(self.t("ps5pkg.err_no_tool"))
                return
            if not wz.dotnet_ordner():
                self._fehler(self.t("ps5pkg.err_no_dotnet"))
                return
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
        if info.ist_quelle and self.format_schluessel == FORMAT_PAKET:
            self._forge_bauen_starten(info, ziel)
            return
        # Umwandeln: ein Paket wird erst entpackt (Arbeitsordner), ein Spielordner geht gleich an Aufgabe 1
        if getattr(self.g, "is_running", False):
            messagebox.showinfo(self.t("ps5pkg.window_title"), self.t("ps5pkg.err_main_busy"), parent=self.win)
            return
        if info.ist_ordner:
            self._protokoll(self.t("ps5pkg.log_start_uebergabe", name=os.path.basename(info.pfad)))
            self.auftrag_var.set(self.t("ps5pkg.job_handoff"))
            self._anzeige_setzen(0, 0)
            self._uebergabe = self._uebergabe_neu("", info, info.pfad)
            if not self._uebergeben(info.pfad):
                self._uebergabe = None
            self._knoepfe_pruefen()
            return
        # Ein Paket schreibt Dump Forge im Strom in das Abbild: ohne Entpacken, ohne Arbeitsordner.
        if direkt:
            self._forge_bauen_starten(info, ziel, abbild=self.format_schluessel)
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

    def _forge_bauen_starten(self, info: "wz.PaketInfo", ziel: str, abbild: str = "") -> None:
        """Baut das Paket mit Dump Forge: Name und Platz pruefen, Arbeitsordner im Zielordner anlegen, los.

        Dump Forge prueft die Quelle selbst (Vorabbefunde, Kennungen, Signaturen) und das Ergebnis danach (Struktur und
        Inhalt) - das Programm legt keine Pruefung davor (anders als bei LibProsperoPkg, wo ``param.json`` vorher
        repariert wird) und keine danach.
        """
        if not self._werkzeug_forge():
            self._fehler(self.t("ps5pkg.err_no_tool_forge"))
            return
        # ``abbild``: das Formatkuerzel (``ffpkg`` usw.), wenn Forge ein Paket direkt in ein Abbild wandelt - im Strom, ohne
        # Entpacken (Nutzerwunsch 17.11.2026: kein Zwischenordner in Aufgabe 7). Leer: das Paket wird gebaut.
        name = self._forge_abbild_name(info, abbild) if abbild else self._forge_dateiname(info)
        datei = os.path.join(ziel, name)
        # Eine Datei gleichen Namens im Ziel wird nur mit dem Haken ersetzt, und erst, wenn die neue fertig und geprueft ist.
        if os.path.exists(datei) and not self.ueberschreiben_var.get():
            messagebox.showinfo(self.t("ps5pkg.window_title"),
                                self.t("ps5pkg.err_exists_abbild" if abbild else "ps5pkg.err_exists_pkg", pfad=datei),
                                parent=self.win)
            return
        if not self._platz_reicht(ziel, int(info.groesse * (ENTPACKT_FAKTOR if abbild else FORGE_PLATZ_FAKTOR)),
                                  nachfragen=True):
            return
        if not abbild and not self._emulatoren_fragen(info):
            return
        # Der Bau entsteht im Zielordner (gleiches Laufwerk: das Umbenennen am Ende kostet nichts), unter einem
        # Arbeitsordner, den das Fenster bei Abbruch oder Fehler wieder entfernt.
        try:
            temp = tempfile.mkdtemp(prefix="ps5conv_forge_", dir=ziel)
        except OSError:
            temp = tempfile.mkdtemp(prefix="ps5conv_forge_", dir=self._arbeitsordner())
        self._staging.append(temp)
        self._bau = {"temp": temp, "vorher": set(os.listdir(ziel)), "forge": True, "format": abbild or "pkg", "name": name}
        self._job_starten("abbild" if abbild else "bauen", self._lauf_bauen, info, ziel)

    def _forge_abbild_name(self, info: "wz.PaketInfo", abbild: str) -> str:
        """Der Name des Abbilds, das Dump Forge aus diesem Paket schreibt: wie bei den Aufgaben 1 bis 6, auf Forges Grenze gekuerzt."""
        endung = next((e for s, _n, e in FORMATE if s == abbild), "." + abbild)
        name = (anzeigename(info) + endung)
        grenze = forge.STAMM_GRENZE_FFPFSC if abbild == "ffpfsc" else forge.STAMM_GRENZE
        return forge.stamm_kuerzen(name, grenze)

    def _quellfakten(self, info: "wz.PaketInfo") -> "forge.QuellFakten | None":
        """Forges Fakten zur Quelle (DLC, PlayGo, AMPR): bei einem Abbild aus dem Lesen, bei einem Spielordner jetzt.

        Einen Spielordner liest ``ffpfsc-pkg-tool`` - Dump Forge sieht ihn erst hier (``inspect``, meist unter einer
        Sekunde; die Listen der Bibliothek bleiben so schnell). Das Ergebnis bleibt an der Quelle haengen.
        """
        faden = getattr(self, "_bericht_faden", None)
        if info.fakten is None and faden is not None and faden[0] is info and faden[1].is_alive():
            faden[1].join(60)                    # die Pruefung der Karte laeuft schon fuer diese Quelle: nicht noch einmal lesen
        if info.fakten is not None:
            return info.fakten
        exe = self._werkzeug_forge()
        if not exe or not (info.ist_ordner or forge.ist_paket(info.pfad)):
            return None
        self._status(self.t("ps5pkg.emu_pruefen"))
        try:
            self.win.update_idletasks()
        except tk.TclError:
            pass
        info.fakten = forge.quellfakten_lesen(exe, info.pfad, popen_extra=self._popen_extra())
        return info.fakten

    def _emulatoren_fragen(self, info: "wz.PaketInfo") -> bool:
        """Vor dem Bau: sucht im Spiel nach AMPR EMU, Asset-Packs, PlayGo, DLC und BACKPORT und fragt, wenn etwas fehlt.

        Nutzerwunsch 17.11.2026: Die Seite soll wie die Aufgaben 1 bis 6 selbst nachsehen und fragen. Die Antwort von Dump
        Forge (``inspect``) steht als Bericht im Protokoll - auch wenn nichts fehlt. Fehlt etwas, das das Spiel braucht,
        fragt das Fenster: Dump Forge uebernimmt die Programmdateien und ``fakelib`` der Quelle unveraendert ins Paket
        (gemessen am Abbild mit AMPR EMU, PlayGo und Backport: das Paket traegt alle drei), ein Paket nimmt also nichts auf.
        Bei einem Spielordner bietet die Frage den Weg an, der es kann: ein Abbild (``.ffpkg``) mit den Kaestchen der
        Aufgabe 1 (:meth:`_als_abbild_mit_einbau`). Bei einem Abbild bleibt nur "trotzdem bauen" - in ein fertiges Abbild laesst
        sich nichts einlegen. AMPR EMU legt Dump Forge fuer ein Spiel, das ``libSceAmpr`` laedt, selbst dazu (Hinweis, keine
        Frage).

        Returns:
            ``False``, wenn nicht gebaut wird (abgebrochen, oder als Abbild neu gestartet).
        """
        fakten, fehlt, liste = self._quelle_pruefen(info, paket=True)
        if not fehlt:
            return True
        if self._abbild_mit_einbau_moeglich(info):
            gewaehlt = self.g._auswahl_dialog(
                self.t("ps5pkg.emu_titel"), self.t("ps5pkg.emu_frage_wahl", liste=liste),
                [self.t("ps5pkg.emu_wahl_abbild"), self.t("ps5pkg.emu_wahl_paket")], parent=self.win)
            if not gewaehlt:
                self._status(self.t("ps5pkg.emu_abgebrochen"))
                return False
            if gewaehlt == self.t("ps5pkg.emu_wahl_abbild"):
                self._als_abbild_mit_einbau(info, fakten, fehlt)
                return False
        elif not messagebox.askyesno(self.t("ps5pkg.emu_titel"), self.t("ps5pkg.emu_frage", liste=liste),
                                     parent=self.win):
            self._status(self.t("ps5pkg.emu_abgebrochen"))
            return False
        self._protokoll(self.t("ps5pkg.emu_log"))
        return True

    def _quelle_pruefen(self, info: "wz.PaketInfo", paket: bool) -> "tuple[forge.QuellFakten | None, list[str], str]":
        """Sucht in der Quelle nach AMPR EMU, Packs, PlayGo, DLC und BACKPORT, schreibt den Bericht und liefert, was fehlt.

        Returns:
            ``(Fakten, Schluessel dessen, was fehlt, die Punkte dazu als Text fuer die Frage)``; ohne Fakten (Quelle nicht
            pruefbar) steht eine Zeile im Protokoll und es fehlt nichts.
        """
        fakten = self._quellfakten(info)
        if fakten is None:
            self._protokoll(self.t("bericht.nicht_pruefbar"))
            return None, [], ""
        # BACKPORT zuerst: Kennt das Programm die Firmware der Konsole nicht, fragt es hier einmal (``_backport_plan``).
        backport = self._backport_zeile(fakten)
        konsole = self.g._konsole_fw_bekannt() or ""
        zeilen = qb.zeilen(fakten, self.t, konsole, forge_ergaenzt_ampr=paket)
        for text in qb.protokoll(zeilen, self.t):
            self._protokoll(text)
        self._protokoll(self.t("bericht.einbau_paket" if paket else "bericht.einbau_nichts"))
        fehlt = [s for s in qb.fehlendes(zeilen) if s != "backport" or backport]
        punkte = {"ampr": lambda: self.t("ps5pkg.emu_zeile_ampr"),
                  "dlc": lambda: self.t("ps5pkg.emu_zeile_dlc", merkmal=fakten.dlc_merkmal or "-"),
                  "playgo": lambda: self.t("ps5pkg.emu_zeile_playgo", merkmal=fakten.playgo_merkmal),
                  "backport": lambda: backport}
        return fakten, fehlt, "\n".join(punkte[s]() for s in fehlt)

    def _abbild_mit_einbau_moeglich(self, info: "wz.PaketInfo") -> bool:
        """Kann dieselbe Quelle als Abbild mit den Kaestchen der Aufgabe 1 entstehen? Nur ein Spielordner, und nur, wenn Aufgabe 1 frei ist."""
        return bool(info.ist_ordner and not getattr(self.g, "is_running", False))

    def _als_abbild_mit_einbau(self, info: "wz.PaketInfo", fakten: "forge.QuellFakten", fehlt: "list[str]") -> None:
        """Haekt an, was fehlt (die Kaestchen der Aufgabe 1), stellt das Format auf ``.ffpkg`` und startet noch einmal.

        Das Format wird **nicht gemerkt** (``_merken``): Es gilt fuer diesen Lauf, die Wahl des Anwenders bleibt. Der Lauf geht
        an Aufgabe 1 und stellt dort die uebrigen Rueckfragen (Fassung und Packverfahren von AMPR EMU usw.).
        """
        namen = self._einbau_ankreuzen(fakten, fehlt)
        self.format_schluessel = "ffpkg"
        self._format_anzeigen()
        self._ergebnis_fuellen()
        self._protokoll(self.t("ps5pkg.emu_abbild_log", liste=", ".join(namen) or "-"))
        self.win.after(150, self._starten)

    def _einbau_ankreuzen(self, fakten: "forge.QuellFakten", fehlt: "list[str]") -> "list[str]":
        """Haekt die Kaestchen der Aufgabe 1 fuer das an, was fehlt (dieselben Wege wie die Rueckfragen dort); liefert ihre Namen."""
        g = self.g
        namen: list[str] = []
        for schluessel in fehlt:
            if schluessel == "ampr" and getattr(g, "_ampr_versionsauswahl", None):
                g._ampr_einschalten()
                namen.append("AMPR EMU")
            elif schluessel == "playgo":
                g._playgo_einschalten()
                namen.append("PlayGo")
            elif schluessel == "dlc":
                g._dlc_einschalten()
                namen.append("DLC EMU")
            elif schluessel == "backport":
                plan = g._backport_plan(fakten, erfragen=False)
                if plan is not None:
                    g._backport_einschalten(plan[1])
                    namen.append("BACKPORT")
        self._einbau_abgleichen()
        return namen

    def _backport_zeile(self, fakten: "forge.QuellFakten") -> str:
        """Die Zeile zu BACKPORT, wenn das Spiel eine neuere Firmware verlangt, als die Konsole hat - sonst ``""``.

        Die Firmware der Konsole kennt das Hauptprogramm (gemessen in der Ansicht KONSOLE); kennt es sie nicht und verlangt
        das Spiel etwas, wird sie jetzt einmal erfragt (dieselbe Frage wie vor einem Lauf der Aufgaben 1 bis 6; ``_backport_plan``).
        Ein Paket nimmt BACKPORT nicht auf - Dump Forge baut die Quelle, wie sie ist -, darum steht es nur als Hinweis da.
        """
        plan = self.g._backport_plan(fakten, erfragen=True)
        if plan is None:
            return ""
        return self.t("ps5pkg.emu_zeile_backport", spiel=fakten.verlangt_text, konsole=self.g._konsole_fw_anzeige(plan[0]))

    # ------------------------------------------------------------------
    # Einbau-Karte, Pruefung der Quelle, Lebenszeichen (Nutzerwunsch 17.11.2026)
    # ------------------------------------------------------------------
    def _einbau_gilt(self) -> bool:
        """Wirkt der Einbau bei dem, was die Seite gerade tut? Nur beim Umwandeln in ein Abbild - ein Paket nimmt ihn nicht auf."""
        return self.aktion_var.get() == AKTION_UMWANDELN and self.format_schluessel != FORMAT_PAKET

    # ------------------------------------------------------------------
    # BAUFORM (Container): nur beim Zielformat .ffpfsc (Nutzerwunsch 17.11.2026: ".ffpfsc ist ein Abbild - gilt das dort nicht auch?")
    # ------------------------------------------------------------------
    def _bauform_reihe_bauen(self, eltern) -> None:
        """BAUFORM (Container) wie bei den Aufgaben 1 bis 6 (``bauform_title``, ``bauform_combo``): Zwilling der Liste dort - dieselbe
        Variable (``bauform_var``), derselbe Befehl (``_on_bauform_changed``), derselbe Tooltip mit dem Vergleich beider Formen.
        Die Reihe steht nur, wenn sie etwas bewirkt (``_BAUFORM_WIRKT_BEI``: der ``.ffpfsc``-Container)."""
        g, c, F, pt = self.g, self.c, self.F, self.pt
        self.bauform_box = None
        self.bauform_reihe = tk.Frame(eltern, bg=c["bg_main"])
        self._bauform_an = False
        self._bauform_tooltip = None
        var, optionen = getattr(g, "bauform_var", None), getattr(g, "_bauform_options", None)
        if var is None or not optionen:
            return
        tk.Label(self.bauform_reihe, text=g._t("bauform.label"), font=(F, pt(9), "bold"), bg=c["bg_main"],
                 fg=c["fg_primary"], anchor="w").pack(side="left", padx=(0, 16))
        self.bauform_box = g._pw.Combobox(self.bauform_reihe, textvariable=var, state="readonly", values=tuple(optionen), font=(F, pt(10)))
        self.bauform_box.bind("<<ComboboxSelected>>", lambda _e: g._on_bauform_changed())
        self.bauform_box.pack(side="left")
        klasse = getattr(sys.modules.get(type(g).__module__), "DelayedTooltip", None)
        if klasse is not None:
            self._bauform_tooltip = klasse(self.bauform_box, g._bauform_erklaerung(), delay_ms=900, wraplength=430)

    def _bauform_sichtbar(self) -> bool:
        """Wirkt die Bauform bei dem, was die Seite tut? Beim Umwandeln in einen ``.ffpfsc`` (wie ``_BAUFORM_WIRKT_BEI`` dort)."""
        return (self.aktion_var.get() == AKTION_UMWANDELN
                and self.format_schluessel in getattr(self.g, "_BAUFORM_WIRKT_BEI", ("ffpfsc",)))

    def _bauform_zeigen(self, an: bool) -> None:
        if self.bauform_box is None:
            return
        if an and self._bauform_tooltip is not None:
            self._bauform_tooltip.text = self.g._bauform_erklaerung()      # der Satz zur gewaehlten Form steht voran
        if an == self._bauform_an:
            return
        self._bauform_an = an
        try:
            self.bauform_reihe.pack(fill="x", pady=(12, 0)) if an else self.bauform_reihe.pack_forget()
        except tk.TclError as exc:
            logger.debug("BAUFORM nicht schaltbar: %s", exc)

    def _bauform_pfs_gewaehlt(self) -> bool:
        """Ist beim Zielformat ``.ffpfsc`` die Bauform "PFS im Container" gewaehlt? Dann baut Dump Forge nicht im Strom."""
        g = self.g
        if self.format_schluessel not in getattr(g, "_BAUFORM_WIRKT_BEI", ("ffpfsc",)):
            return False
        exfat = getattr(_haupt(g), "BAUFORM_EXFAT", "exfat")
        return str(getattr(g, "bauform", exfat)) != exfat

    def _einbau_abgleichen(self) -> None:
        """Zieht Auswahllisten und Sperren der Einbau-Karte aus dem Hauptfenster nach (im Takt, nur wenn die Seite zu sehen ist)."""
        karte = self.einbau
        if karte is None or not self._rest_sichtbar:
            return
        gilt = self._einbau_gilt()
        wirkt = gilt and self.format_schluessel in getattr(self.g, "_KOMPRESSION_WIRKT_BEI", ("ffpfsc",))
        karte.abgleichen(gilt, wirkt)
        karte.format_hinweis_setzen(self._format_hinweis())
        self._bauform_zeigen(self._bauform_sichtbar())

    def _format_hinweis(self) -> str:
        """Der Hinweis unter dem ZIELFORMAT, wie ``_zielformat_hinweis`` im Hauptfenster: das Ziel, bei den PFS-Containern das
        Tempo samt Empfehlung, sonst die Einstufung des Autors von ShadowMount+ - und beim Paket, dass der Einbau nichts bewirkt."""
        t = self.t
        if self.aktion_var.get() != AKTION_UMWANDELN:
            return ""
        if self.format_schluessel == FORMAT_PAKET:
            return t("ps5pkg.einbau_nur_abbild")
        if self.format_schluessel in FORMATE_MIT_RUCKELHINWEIS:
            return "\n".join((t("main.ziel_hint", formats="ffpfsc/ffpfs"), t("main.pfs_speed_hint")))
        endung = next((e for s, _n, e in FORMATE if s == self.format_schluessel), "")
        zeilen = [t("main.ziel_hint", formats=endung)]
        einstufung = getattr(self.g, "_SMP_EINSTUFUNG", {}).get(self.format_schluessel)
        if einstufung:
            zeilen.append(t(einstufung))
        return "\n".join(zeilen)

    def _bericht_aktualisieren(self) -> None:
        """Wie in den Aufgaben 1 bis 6: Ist eine Quelle gewaehlt, steht im Protokoll, was in dem Spiel schon eingebaut ist
        (BACKPORT, AMPR EMU, Asset-Pack, PlayGo) - und, wenn nichts eingebaut ist, ob das Spiel PlayGo braeuchte.

        Nutzerwunsch 17.11.2026: "es soll automatisch im Spiel nach DLC, PlayGo, LZ4, zstd und AMPR EMU Inhalt gesucht
        werden, wie in Aufgabe 1-6 bereits". Es sind dieselben ``[Pruefung]``-Zeilen (``_quelle_einbauten_zeilen`` des
        Hauptfensters), einmal je Quelle und Stand. Gelesen wird im Hintergrund, das Fenster bleibt bedienbar; eine Antwort, die
        zu einer inzwischen anderen Quelle gehoert, wird verworfen. Danach liest Dump Forge die Fakten fuer die Rueckfragen vor
        dem Lauf vor (``inspect``, meist unter einer Sekunde) - ein Bau, der waehrenddessen startet, wartet darauf
        (``_quellfakten``) und liest nicht ein zweites Mal.
        """
        info = self.aktuell
        if info is None:
            return
        try:
            schluessel = (os.path.normcase(os.path.abspath(info.pfad)), int(os.path.getmtime(info.pfad)))
        except OSError:
            return
        if schluessel == self._einbauten_gemeldet:
            return                                   # die Liste meldet eine Wahl mehrfach
        self._einbauten_gemeldet = schluessel
        exe = self._werkzeug_forge()
        popen_extra = self._popen_extra()

        def lauf() -> None:
            zeilen = None
            try:
                zeilen = self.g._quelle_einbauten_zeilen(info.pfad, lambda: self.aktuell is info)
            except Exception as exc:  # noqa: BLE001 - eine Auskunft, kein Hindernis fuer den Lauf
                logger.debug("Einbauten von %s nicht pruefbar: %s", info.pfad, exc)
            # Gemeldet wird im Takt des Fensters (``_takt_arbeiten``), wie alles, was ein Faden meldet: Ein Faden fasst
            # kein Widget an, und ``after`` aus einem Faden braucht die laufende Hauptschleife.
            with self._sperre:
                self._z["bericht"].append((info, zeilen))
            if info.fakten is None and exe and (info.ist_ordner or forge.ist_paket(info.pfad)):
                fakten = forge.quellfakten_lesen(exe, info.pfad, popen_extra=popen_extra)
                if fakten is not None:
                    info.fakten = fakten

        faden = threading.Thread(target=lauf, daemon=True, name="ps5pkg-bericht")
        self._bericht_faden = (info, faden)
        faden.start()

    @staticmethod
    def _dauer_text(sekunden: float) -> str:
        """``3:07`` oder ``1:02:09`` - so lange laeuft etwas schon."""
        s = max(0, int(sekunden))
        h, rest = divmod(s, 3600)
        m, s = divmod(rest, 60)
        return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)

    def _werkzeug_name(self, art: str, info: "wz.PaketInfo") -> str:
        """Welches Werkzeug den Auftrag ausfuehrt, wie der Anwender es kennt: Dump Forge baut, LibProsperoPkg liest, prueft und entpackt."""
        return "Dump Forge" if art in ("bauen", "abbild") else "LibProsperoPkg"

    #: Ab so vielen Sekunden ohne neue Meldung sagt die Seite, dass nichts Neues kam (und dass das bei grossen Dateien normal ist).
    STILLE_AB = 20.0

    def _lebenszeichen_zeigen(self) -> None:
        """Wie lange der Lauf schon geht, mit welchem Werkzeug - und wenn es still wird, seit wann nichts Neues kam.

        Nutzerwunsch 17.11.2026: "man sieht nicht, ob etwas passiert, oder ob das Programm haengt". Der Zaehler laeuft im Takt
        des Fensters, unabhaengig vom Werkzeug; stehen Fortschritt und Dateizeile still, sagt die zweite Zeile es offen.
        """
        job = self._job
        if job is None:
            if self._uebergabe is None:
                self._lebt_setzen("")
            return
        jetzt = time.monotonic()
        start = job.get("start") or jetzt
        text = self.t("ps5pkg.lebt_zeit", dauer=self._dauer_text(jetzt - start),
                      werkzeug=self._werkzeug_name(job.get("art", ""), job.get("info")) if job.get("info") is not None else "")
        still = jetzt - (job.get("letzte") or jetzt)
        if still >= self.STILLE_AB:
            text += "\n" + self.t("ps5pkg.lebt_still", still=self._dauer_text(still))
        self._lebt_setzen(text)

    def _lebt_setzen(self, text: str) -> None:
        """Das Lebenszeichen rechts unten (klein, unter der Statuszeile); ohne Text ganz aus dem Raster, wie ``telemetry_label``."""
        if self.lebt_var.get() != text:
            self.lebt_var.set(text)
        try:
            if text and not self.lebt_label.winfo_ismapped():
                self.lebt_label.grid()
            elif not text and self.lebt_label.winfo_manager():
                self.lebt_label.grid_remove()
        except tk.TclError:
            pass

    def _abbild_direkt_moeglich(self, info: "wz.PaketInfo") -> bool:
        """Kann Dump Forge dieses ``.pkg`` im Strom in das gewaehlte Abbild schreiben - ohne Entpacken, ohne Zwischenordner?

        Nutzerwunsch 17.11.2026 ("im Strom bauen wie bei Aufgabe 1 bis 6"). Gemessen: ``convert x.pkg --to ffpkg|exfat|folder``
        liest das Paket im Strom. Der Einbau (AMPR EMU, PlayGo, DLC EMU, BACKPORT) braucht den entpackten Ordner - dann bleibt
        der Weg ueber den Arbeitsordner und Aufgabe 1. Fehlt dem Spiel etwas, fragt das Fenster, ob entpackt und eingebaut wird.
        """
        if info.ist_quelle or self.format_schluessel not in forge.ABBILD_ZIELE:
            return False
        if not self._werkzeug_forge() or not forge.ist_paket(info.pfad):
            return False
        if self._bauform_pfs_gewaehlt():
            # Dump Forge baut im Strom nur die Bauform exFAT im Container; wer "PFS im Container" gewaehlt hat, bekommt sie vom Weg
            # ueber Aufgabe 1 - nicht still die andere (wie ``_strom_nach_container_gewaehlt`` dort).
            self._protokoll(self.t("ps5pkg.log_bauform_braucht_ordner"))
            return False
        liste = self.g._einbau_liste()
        if liste:
            self._protokoll(self.t("ps5pkg.log_einbau_braucht_ordner", liste=", ".join(liste)))
            return False
        fakten, fehlt, punkte = self._quelle_pruefen(info, paket=False)
        if fehlt and messagebox.askyesno(self.t("ps5pkg.emu_titel"), self.t("ps5pkg.emu_frage_entpacken", liste=punkte),
                                         parent=self.win):
            namen = self._einbau_ankreuzen(fakten, fehlt)
            self._protokoll(self.t("ps5pkg.log_einbau_braucht_ordner", liste=", ".join(namen) or "-"))
            return False
        return True

    def _forge_stufe_text(self, stufe: str) -> str:
        """Die Stufe aus Forges Fortschrittsstrom in der Sprache des Programms (unbekannte Stufen bleiben, wie sie sind)."""
        return self.t("ps5pkg.forge_stage_" + stufe) if stufe in FORGE_STUFEN else stufe

    def _lauf_bauen_forge(self, info: "wz.PaketInfo", ziel: str, bau: dict) -> dict:
        """Arbeitsfaden: ``convert --to pkg`` in den Arbeitsordner, danach das fertige Paket an seinen Platz im Ziel."""
        def fortschritt(prozent: int, stufe: str) -> None:
            with self._sperre:
                self._z["prozent"] = float(prozent)
                self._z["gesamt"] = float(prozent)
                self._z["schritt_text"] = self._forge_stufe_text(stufe)

        try:
            temp = str(bau.get("temp") or "")
            abbild = str(bau.get("format") or "pkg")
            name = str(bau.get("name") or "") or self._forge_dateiname(info)
            kraken = str(self._einstellung(opt.FORGE_KRAKEN, opt.STANDARD[opt.FORGE_KRAKEN]))
            if abbild == "pkg":
                erg = forge.bauen(
                    self._werkzeug_forge(), info.pfad, os.path.join(temp, name),
                    kraken=kraken if kraken in forge.KRAKEN_STUFEN else "fast",
                    voll_pruefen=bool(self._einstellung(opt.FORGE_VOLL_PRUEFEN, False)),
                    backport_entfernen=bool(self._einstellung(opt.FORGE_BACKPORT_ENTFERNEN, False)),
                    kerne=int(self._einstellung(opt.KRAKEN_KERNE, 0)),
                    zeile=self._melden, fortschritt=fortschritt, abbruch=lambda: self._abbruch,
                    popen_extra=self._popen_extra())
            else:
                # Ein Abbild aus einem Paket: Die Felder KOMPRESSION (PFS), WORKER-THREADS und PRUEFUNG der Karte gelten
                # (dieselben Einstellungen wie in den Aufgaben 1 bis 6, gelesen aus dem Speicher - nie eine Tk-Variable im Faden).
                try:
                    stufe = int(self.g._load_setting("zstd_level", 6))
                except (TypeError, ValueError):
                    stufe = 6
                try:
                    kerne = int(self.g._load_setting("worker_count", 0) or 0)
                except (TypeError, ValueError):
                    kerne = 0
                erg = forge.bauen(
                    self._werkzeug_forge(), info.pfad, os.path.join(temp, name), format=abbild, stufe=stufe, kerne=kerne,
                    voll_pruefen=str(self.g._load_setting("mkpfs_verify", "schnell") or "") == "voll",
                    zeile=self._melden, fortschritt=fortschritt, abbruch=lambda: self._abbruch,
                    popen_extra=self._popen_extra())
            with self._sperre:
                self._z["prozent"] = 100.0
                self._z["gesamt"] = 100.0
                self._z["schritt_text"] = self._forge_stufe_text("finalize")
            endgueltig = os.path.join(ziel, name)
            if os.path.exists(endgueltig):
                os.remove(endgueltig)               # nur mit dem Haken "Vorhandene ersetzen" (siehe _forge_bauen_starten)
            try:
                os.replace(erg.pfad, endgueltig)
            except OSError:                         # Arbeitsordner auf einem anderen Laufwerk
                shutil.move(erg.pfad, endgueltig)
        except wz.Fehler as exc:
            return self._ende_bei_fehler(exc)
        except OSError as exc:
            logger.exception("Paket von Dump Forge ablegen")
            return {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket bauen mit Dump Forge")
            return {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        t = self.t
        if erg.modus == "full":
            pruefung = t("ps5pkg.forge_check_full", n=len(erg.pruefungen), gesamt=self._fmt(erg.gesamt_bytes))
        else:
            pruefung = t("ps5pkg.forge_check_fast", n=len(erg.pruefungen), geprueft=self._fmt(erg.geprueft_bytes),
                         gesamt=self._fmt(erg.gesamt_bytes), proben=erg.proben)
        return {"ok": True, "text": endgueltig, "ausgabe": ziel, "pkg": endgueltig, "pruefung": pruefung, "befund": False}

    def _job_starten(self, art: str, ziel_funktion, info: "wz.PaketInfo", ziel: str) -> None:
        # Der Haken "Quelle nach Erfolg loeschen": vor dem Start bestaetigen, nie still. Abbrechen startet nichts.
        weiter, loeschen = self._loeschen_vorbereiten(art, info)
        if not weiter:
            self._staging_raeumen()
            self._bau = None
            return
        self._abbruch = False
        jetzt = time.monotonic()
        # "start" und "letzte" fuer das Lebenszeichen (``_lebenszeichen_zeigen``): seit wann der Lauf geht, wann zuletzt etwas kam.
        self._job = {"art": art, "info": info, "ziel": ziel, "start": jetzt, "letzte": jetzt, "zeichen": None,
                     "loeschen": loeschen}
        with self._sperre:
            # "prozent" erst mit der ersten Meldung des Laufs: Beim Pruefen kommt keine, der Balken wandert dann.
            self._z.update({"prozent": None, "fertig": None, "ausgabe": "", "gesamt": None, "schritt_text": None})
        self._anzeige_setzen(0, 0)
        self.datei_var.set("")
        text = {"pruefen": "ps5pkg.job_checking", "extrahieren": "ps5pkg.job_extracting",
                "umwandeln": "ps5pkg.job_extracting_for", "bauen": "ps5pkg.job_building",
                "abbild": "ps5pkg.job_abbild", "konsole": "ps5pkg.job_console"}[art]
        self.auftrag_var.set(self.t(text, name=anzeigename(info)))
        # Auch die Statuszeile sagt, dass gearbeitet wird - sie stand bisher waehrend des ganzen Laufs auf "Bereit."
        self._status(self.t(text, name=anzeigename(info)))
        if art == "pruefen":
            self._balken_wandern(True)
        self._protokoll(self.t("ps5pkg.log_start_" + art, name=os.path.basename(info.pfad)))
        # Womit gearbeitet wird (Nutzerwunsch 17.11.2026): das Protokoll nennt das Werkzeug.
        if art in ("bauen", "abbild"):
            self._protokoll(self.t("ps5pkg.log_bauer", name=self._werkzeug_name(art, info)))
        self._knoepfe_pruefen()
        threading.Thread(target=ziel_funktion, args=(info, ziel, art), daemon=True, name="ps5pkg-" + art).start()

    def _ende_bei_fehler(self, exc: Exception) -> dict:
        """Das Ende eines Laufs, der mit ``exc`` endete: nach ABBRECHEN ein Abbruch, sonst ein Fehlschlag.

        Bis zum 03.11.2026 stand nach ABBRECHEN "Fehlgeschlagen" und "[FEHLER] abgebrochen" da.
        """
        if self._abbruch:
            return {"ok": True, "abgebrochen": True, "text": self.t("ps4pkg.status_cancelled")}
        return {"ok": False, "text": str(exc)}

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
            ende = self._ende_bei_fehler(exc)
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
            schluss = wz.extrahieren(self._werkzeug(), info.pfad, ziel, passcode=self._passcode(),
                                     zeile=self._melden, fortschritt=fortschritt,
                                     abbruch=lambda: self._abbruch, popen_extra=self._popen_extra(),
                                     platz_pruefen=lambda gesamt: self._platz_fuer_entpacken(ziel, gesamt))
            ende = {"ok": True, "text": schluss, "ausgabe": ziel}
        except wz.Fehler as exc:
            ende = self._ende_bei_fehler(exc)
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
            ende = self._ende_bei_fehler(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Paket auf die PS5 entpacken")
            ende = {"ok": False, "text": "%s: %s" % (type(exc).__name__, exc)}
        with self._sperre:
            self._z["fertig"] = ende

    def _lauf_bauen(self, info: "wz.PaketInfo", ziel: str, art: str) -> None:
        """Arbeitsfaden: Dump Forge baut das Paket (bei ``art == "abbild"`` das Abbild aus dem Paket) und prueft es danach selbst."""
        bau = getattr(self, "_bau", {}) or {}
        ende = self._lauf_bauen_forge(info, ziel, bau)
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
            self._uebergabe["abgebrochen"] = True
            self._status(self.t("ps5pkg.status_cancelling"))
            try:
                self.g._kill_task()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Abbruch der Aufgabe 1: %s", exc)

    # ------------------------------------------------------------------
    # Hand-off an Aufgabe 1
    # ------------------------------------------------------------------
    def _uebergabe_neu(self, staging: str, info: "wz.PaketInfo", quelle: str) -> dict:
        """Der Stand der Uebergabe an Aufgabe 1 - samt dem, was vorher im Ziel lag (fuer einen Abbruch)."""
        ziel = self.ziel_var.get().strip()
        try:
            vorher = sorted(os.listdir(ziel)) if ziel and os.path.isdir(ziel) else None
        except OSError:
            vorher = None
        return {"staging": staging, "gesehen": False, "info": info, "ziel": ziel, "ziel_vorher": vorher,
                "name": os.path.basename(os.path.normpath(quelle)) if quelle else ""}

    def _uebergeben(self, staging: str, quelle_schon_gefragt: bool = False) -> bool:
        """Traegt den entpackten Ordner in Aufgabe 1 ein und startet sie.

        ``quelle_schon_gefragt``: ``staging`` ist ein Arbeitsordner, nicht die Quelle des Anwenders - die Rueckfrage zu "Quelle nach
        Erfolg loeschen" hat Seite 7 beim Start gestellt (fuer das Paket), Aufgabe 1 soll nicht noch einmal nach dem Arbeitsordner
        fragen. Der Haken bleibt dabei, wie er war."""
        g = self.g
        ziel = self.ziel_var.get().strip()
        var = getattr(g, "quelle_loeschen_var", None)
        war = None
        if quelle_schon_gefragt and var is not None:
            war = bool(var.get())
            var.set(False)
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
        finally:
            if war is not None and var is not None:
                var.set(war)
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
            berichte, self._z["bericht"] = self._z.get("bericht", []), []
        for quelle, einbauten in berichte:
            if self.aktuell is quelle and einbauten:    # die Antwort einer inzwischen anderen Quelle zeigt niemand
                for text in einbauten:
                    self._protokoll(text.rstrip("\n"))
        with self._sperre:
            nachlauf, self._z["nachlauf"] = self._z["nachlauf"], []
        for art, ergebnis in nachlauf:
            self._nachlauf = False
            self._nach_erfolg_weiter(art, ergebnis)
        if self._job is not None:
            # Etwas Neues kam: eine Zeile des Werkzeugs, ein anderer Prozentwert oder eine andere Dateizeile (Lebenszeichen).
            zeichen = (prozent, datei)
            if zeilen or zeichen != self._job.get("zeichen"):
                self._job["letzte"] = time.monotonic()
                self._job["zeichen"] = zeichen
        for z in zeilen:
            self._protokoll(z)
        if scan:
            self._scan_uebernehmen(scan)
        for paket_liste, waehlen in gelesen:
            self._gelesen_uebernehmen(paket_liste, waehlen)
        if gelesen and liest and self._job is None:
            self._status(self.t("ps5pkg.status_reading", count=liest))     # ein weiteres Lesen laeuft noch
        if prozent is not None and self._job is not None:
            self._anzeige_setzen(prozent, gesamt if gesamt is not None
                                 else prozent if self._job["art"] != "umwandeln" else prozent / 2.0)
            if datei:
                # Nur der Dateiname, nicht der Ordnerpfad im Spiel - sonst lief die Zeile rechts aus der Karte. Das gilt
                # nur fuer einen Pfad: Eine Meldung des Baus ("... (SHA3/ihsh/rhsh): started (2,462 blocks total)")
                # wurde sonst am letzten "/" zerschnitten und zeigte " 2,462 blocks)." (gemessen 03.11.2026).
                erster, _trenner, rest = datei.partition(" \u00b7 ")
                kurz = erster
                if _PFADARTIG.match(erster):
                    kurz = erster.replace("\\", "/").rsplit("/", 1)[-1] or erster
                self.datei_var.set(kurz + (" \u00b7 " + rest if rest else ""))
        if fertig is not None and self._job is not None:
            self.datei_var.set("")
            self._job_beendet(fertig)
        if self._uebergabe is not None:
            self._uebergabe_beobachten()
        self._einbau_abgleichen()
        self._lebenszeichen_zeigen()
        self._fortschritt_zeigen(self._job is not None)
        groesse = self._groesse_text()
        if self.groesse_var.get() != groesse:
            self.groesse_var.set(groesse)

    def _job_beendet(self, ende: dict) -> None:
        job, self._job = self._job, None
        art = job["art"]
        self._balken_wandern(False)
        self._status(self.t("ps5pkg.status_idle"))
        self.lebt_var.set("")
        if ende.get("nichts") or ende.get("abgebrochen"):
            # Der Anwender hat bei der Rueckfrage verzichtet oder abgebrochen: kein Fehlschlag. Ein abgebrochener Lauf
            # zeigt 0 % (nicht den Stand beim Abbruch) - fertig ist nichts.
            self.auftrag_var.set(ende["text"])
            self._protokoll(ende["text"])
            if ende.get("nichts") or art != "konsole":
                self._anzeige_setzen(0, 0)
            if ende.get("abgebrochen"):
                self._lauf_reste_wegraeumen(job)
            self._knoepfe_pruefen()
            return
        if not ende["ok"]:
            self.auftrag_var.set(self.t("ps5pkg.job_failed"))
            self._protokoll(self.t("ps5pkg.log_failed", grund=ende["text"]))
            self._anzeige_setzen(0, 0)
            self._lauf_reste_wegraeumen(job)
            self._knoepfe_pruefen()
            return
        if art == "bauen":
            self._staging_raeumen()
            self.auftrag_var.set(self.t("ps5pkg.job_done_build", datei=os.path.basename(ende["pkg"])))
            self._protokoll(self.t("ps5pkg.log_built", pfad=ende["pkg"]))
            self._protokoll(("[BEFUND] " if ende.get("befund") else "[OK] ") + ende["pruefung"])
            # Der Hinweis zum Start an der Konsole nennt "das Werkzeug" (ps5-fpkg-converter) - fuer ein Paket von Dump Forge
            # gilt Forges eigener Hinweis (kstuff, fpkg-enable, ppr-patch).
            self._protokoll(self.t("ps5pkg.forge_note"))
            with self._sperre:
                self._z["ausgabe"] = job["ziel"]
            self._anzeige_setzen(100, 100)
            self._knoepfe_pruefen()
            self._nach_erfolg("bauen", ende["pkg"], job.get("loeschen"), bool(ende.get("befund")))
            return
        if art == "abbild":
            # Dump Forge hat das Paket im Strom in ein Abbild geschrieben (kein Entpacken, kein Zwischenordner).
            self._staging_raeumen()
            self.auftrag_var.set(self.t("ps5pkg.job_done_convert"))
            self._protokoll(self.t("ps5pkg.log_done_convert", name=os.path.basename(ende["pkg"])))
            self._protokoll(("[BEFUND] " if ende.get("befund") else "[OK] ") + ende["pruefung"])
            with self._sperre:
                self._z["ausgabe"] = job["ziel"]
            self._anzeige_setzen(100, 100)
            self._knoepfe_pruefen()
            self._ausgabe_nach_erfolg()
            self._nach_erfolg("abbild", ende["pkg"], job.get("loeschen"), bool(ende.get("befund")))
            return
        if art == "pruefen":
            self.auftrag_var.set(ende["text"])
            self._protokoll(("[BEFUND] " if ende.get("befund") else "[OK] ") + ende["text"])
            self._anzeige_setzen(100, 100)
            self._knoepfe_pruefen()
            self._nach_erfolg("pruefen", "", None, bool(ende.get("befund")))
            return
        if art == "konsole":
            self.auftrag_var.set(self.t("ps5pkg.job_done_console", ziel=job["ziel"]))
            self._protokoll(ende["text"])
            self._anzeige_setzen(100, 100)
            self._knoepfe_pruefen()
            self._nach_erfolg("konsole", "", None)
            return
        if art == "extrahieren":
            self.auftrag_var.set(self.t("ps5pkg.job_done_extract", ordner=job["ziel"]))
            self._protokoll(ende["text"])
            with self._sperre:
                self._z["ausgabe"] = job["ziel"]
            self._anzeige_setzen(100, 100)
            self._knoepfe_pruefen()
            self._ausgabe_nach_erfolg()
            self._nach_erfolg("extrahieren", job["ziel"], job.get("loeschen"))
            return
        # umwandeln: entpackt - nun Aufgabe 1
        self._protokoll(ende["text"])
        self.auftrag_var.set(self.t("ps5pkg.job_handoff"))
        self._uebergabe = self._uebergabe_neu(job["ziel"], job["info"], job["ziel"])
        self._uebergabe["loeschen"] = job.get("loeschen")      # die Quelle ist die des Pakets, nicht der Arbeitsordner
        self._anzeige_setzen(0, 50)
        if not self._uebergeben(job["ziel"], quelle_schon_gefragt=True):
            self._uebergabe = None
            self._staging_raeumen()
        self._knoepfe_pruefen()

    def _lauf_reste_wegraeumen(self, job: dict) -> None:
        """Nach Abbruch oder Fehlschlag: was der Lauf halb angelegt hat (Arbeitsordner, halber Spielordner)."""
        art = job.get("art")
        if art in ("umwandeln", "bauen", "abbild"):
            self._staging_raeumen()
        elif art == "extrahieren":
            self._teilergebnis_wegraeumen(job.get("ziel", ""))

    def _a1_arbeitet_noch(self) -> bool:
        """Arbeitet Aufgabe 1 noch - ihr Faden oder ein nach dem Abbruch weiterlaufendes mkpfs?"""
        g = self.g
        laeuft_noch = getattr(g, "_vorgang_laeuft_noch", None)
        if callable(laeuft_noch) and laeuft_noch():
            return True
        offen = getattr(g, "_pending_mkpfs_engine_done", None)
        return isinstance(offen, threading.Event) and not offen.is_set()

    def _abbruch_ergebnis_wegraeumen(self, u: dict) -> None:
        """Nach ABBRECHEN waehrend Aufgabe 1: was dabei neu im Ziel entstand und den Namen des Spiels traegt, ist kein
        gewolltes Ergebnis (``<Name>.ffpfsc``, ``.tmp``, ``.partial``) - es wird entfernt."""
        ziel, vorher, name = u.get("ziel", ""), u.get("ziel_vorher"), u.get("name", "")
        if not ziel or vorher is None or not name or not os.path.isdir(ziel):
            return
        try:
            neu = [n for n in set(os.listdir(ziel)) - set(vorher) if n.startswith(name)]
        except OSError:
            return
        for eintrag in neu:
            pfad = os.path.join(ziel, eintrag)
            try:
                if os.path.isdir(pfad):
                    _haupt(self.g)._rmtree_force(pfad, ignore_errors=True)
                else:
                    os.remove(pfad)
                self._protokoll(self.t("ps5pkg.log_removed_partial", pfad=pfad))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Teilergebnis %s nicht entfernbar: %s", pfad, exc)

    def _a1_stand_zeigen(self) -> None:
        """Waehrend Aufgabe 1 umwandelt: ihren Fortschritt auch hier zeigen (zweite Haelfte des Gesamtbalkens).

        Gemeldet am 03.11.2026: Nach dem Entpacken stand die Seite minutenlang still auf 100 % / 50 % - ob noch etwas
        geschah, war nicht zu sehen.
        """
        g = self.g
        self._status(self.t("ps5pkg.job_handoff"))
        try:
            prozent = max(0.0, min(100.0, float(g.progress_var.get())))
        except (AttributeError, tk.TclError, ValueError):
            return
        # Ein Spielordner geht ohne Entpacken an Aufgabe 1: Dann ist ihr Fortschritt der ganze Lauf.
        entpackt = bool((self._uebergabe or {}).get("staging"))
        self._anzeige_setzen(prozent, 50.0 + prozent / 2.0 if entpackt else prozent)
        try:
            text = str(g.size_label.cget("text") or "")
        except (AttributeError, tk.TclError):
            text = ""
        self.datei_var.set(text)

    def _uebergabe_beobachten(self) -> None:
        laeuft = bool(getattr(self.g, "is_running", False))
        u = self._uebergabe
        if laeuft:
            u["gesehen"] = True
            if not u.get("abgebrochen"):
                self._a1_stand_zeigen()
            return
        if u.get("abgebrochen"):
            # ``_kill_task`` setzt ``is_running`` sofort zurueck, mkpfs (im Programm, nicht unterbrechbar) liest aber
            # noch im Arbeitsordner und schreibt ins Ziel: Erst nach seinem Ende wird geraeumt. Gemessen 03.11.2026:
            # ohne das Warten FileNotFoundError in mkpfs und eine halbe ".ffpfsc.tmp" im Ziel; mit dem Warten auf den
            # Aufgabenfaden allein eine fertige ".ffpfsc" trotz Abbruch.
            if self._a1_arbeitet_noch():
                return
            self._abbruch_ergebnis_wegraeumen(u)
            self._uebergabe = None
            self.datei_var.set("")
            self._status(self.t("ps5pkg.status_idle"))
            self.auftrag_var.set(self.t("ps4pkg.status_cancelled"))
            self._protokoll(self.t("ps4pkg.status_cancelled"))
            self._anzeige_setzen(0, 0)
            self._staging_raeumen()
            self._knoepfe_pruefen()
            return
        if not u["gesehen"]:
            # Aufgabe 1 hat gar nicht angefangen (Rueckfrage verneint, Pruefung gescheitert)
            u["wartezeit"] = u.get("wartezeit", 0) + 1
            if u["wartezeit"] * TAKT_MS < 4000:
                return
        if u["gesehen"] and self._a1_arbeitet_noch():
            return                        # Aufgabe 1 raeumt noch auf - erst danach den Arbeitsordner entfernen
        ok = bool(getattr(self.g, "_last_task_ok", False)) and u["gesehen"]
        self._uebergabe = None
        self.datei_var.set("")
        self._status(self.t("ps5pkg.status_idle"))
        if ok:
            self.auftrag_var.set(self.t("ps5pkg.job_done_convert"))
            self._anzeige_setzen(100, 100)
            self._protokoll(self.t("ps5pkg.log_done_convert", name=self._ziel_name()))
            self._ausgabe_nach_erfolg()
            if u.get("loeschen"):                 # Senden und Herunterfahren hat Aufgabe 1 selbst erledigt; die Quelle loescht Seite 7
                self._nach_erfolg("umwandeln", str(getattr(self.g, "task_final_output_path", "") or ""), u["loeschen"])
        else:
            self.auftrag_var.set(self.t("ps5pkg.job_failed"))
            self._anzeige_setzen(0, 0)
            self._protokoll(self.t("ps5pkg.log_convert_not_done"))
        self._staging_raeumen()
        self._knoepfe_pruefen()

    # ------------------------------------------------------------------
    # Nach einem Erfolg: Quelle loeschen, Ergebnis an die PS5 senden, Rechner herunterfahren (Nutzerwunsch 17.11.2026: die Haken
    # der Aufgaben 1 bis 6 auch hier). Dieselben Tk-Variablen, Einstellungen, Rueckfragen und Texte wie dort.
    # ------------------------------------------------------------------
    #: Auftraege, die ein Ergebnis auf dem Rechner hinterlassen: nur bei ihnen gilt "Quelle nach Erfolg loeschen".
    ERGEBNIS_ARTEN = ("bauen", "abbild", "extrahieren", "umwandeln")
    #: Auftraege, nach denen Seite 7 selbst "Vorgang erfolgreich abgeschlossen" meldet. Bei ``umwandeln`` laeuft Aufgabe 1, und die
    #: meldet es dort selbst (``_finish_success`` im Hauptfenster) - eine zweite Meldung waere doppelt.
    MELDUNG_ARTEN = ("bauen", "abbild", "extrahieren")

    #: Die fuenf Haken unter dem Zielordner in der Reihenfolge, in der sie die Spalten fuellen (von oben nach unten, dann nach rechts).
    HAKEN_REIHENFOLGE = ("ueberschreiben", "arbeitskopie", "herunterfahren", "senden", "loeschen")
    #: Hoechstens so viele Spalten nebeneinander; Abstand zwischen den Spalten in Pixeln.
    HAKEN_SPALTEN_MAX = 3
    HAKEN_ABSTAND = 32

    def _nach_erfolg_haken_bauen(self, quelle) -> None:
        """Die Haken unter dem Zielordner: "Vorhandenes ueberschreiben", die Arbeitskopie und die drei Haken der Aufgabe 1
        (herunterfahren, senden, Quelle loeschen), auf so viele Spalten verteilt, wie nebeneinander passen.

        Die drei Haken der Aufgabe 1 und die Arbeitskopie sind Zwillinge der Haken im Hauptfenster (gleiche Variablen, gleiche
        Befehle): Eine Wahl hier gilt dort und umgekehrt. Die Arbeitskopie wirkt, wo in einen Spielordner eingebaut wird (der
        Weg ueber Aufgabe 1)."""
        g, c, F, pt = self.g, self.c, self.F, self.pt
        rahmen = tk.Frame(quelle, bg=c["bg_main"])
        rahmen.pack(fill="x", pady=(6, 0))
        self.nach_erfolg_rahmen = rahmen
        self.nach_erfolg_haken: "dict[str, object]" = {}
        self.ueberschreiben = g._pw.Checkbutton(rahmen, text=self.t("ps5pkg.overwrite"), variable=self.ueberschreiben_var,
                                                font=(F, pt(9)))
        self.nach_erfolg_haken["ueberschreiben"] = self.ueberschreiben
        # (Name, Text, Variable im Hauptfenster, Befehl dort)
        for name, text, variable, befehl in (
                ("herunterfahren", "main.shutdown_after_success", "shutdown_after_success", "_on_shutdown_setting_changed"),
                ("senden", "main.senden_nach_erfolg", "senden_nach_erfolg_var", "_on_senden_nach_erfolg_changed"),
                ("loeschen", "main.quelle_loeschen", "quelle_loeschen_var", ""),
                ("arbeitskopie", "main.arbeitskopie_vorher", "arbeitskopie_vorher", "_on_arbeitskopie_setting_changed")):
            var = getattr(g, variable, None)
            if var is None:
                continue
            kommando = getattr(g, befehl, None) if befehl else None
            self.nach_erfolg_haken[name] = g._pw.Checkbutton(rahmen, text=g._t(text), variable=var, command=kommando,
                                                            font=(F, pt(9)))
        self._ueberschreiben_zeigen = True
        self._haken_ort: "tuple | None" = None
        self._haken_anordnen(0)         # zunaechst schmal (eine Spalte); das erste <Configure> verteilt sie auf die wirkliche Breite
        rahmen.bind("<Configure>", lambda e: self._haken_anordnen(e.width) if e.width > 1 else None, add="+")

    def _haken_spalten(self, sichtbar: "list[str]", breite: int) -> "list[list[str]]":
        """Verteilt die Haken auf drei, zwei oder eine Spalte - auf so viele, wie in ``breite`` Pixel nebeneinander passen.

        Jede Spalte wird von oben nach unten gefuellt (bei fuenf Haken und drei Spalten 2 + 2 + 1, bei zwei Spalten 3 + 2), die
        Karte bleibt so niedrig wie moeglich. Reicht die Breite fuer zwei Spalten nicht, stehen alle untereinander."""
        haken = self.nach_erfolg_haken
        for n in range(self.HAKEN_SPALTEN_MAX, 1, -1):
            zeilen = -(-len(sichtbar) // n)
            spalten = [sichtbar[i:i + zeilen] for i in range(0, len(sichtbar), zeilen)]
            noetig = sum(max(int(haken[h].winfo_reqwidth()) for h in s) for s in spalten) + self.HAKEN_ABSTAND * (len(spalten) - 1)
            if noetig <= breite:
                return spalten
        return [list(sichtbar)]

    def _haken_anordnen(self, breite: int) -> None:
        """Legt die sichtbaren Haken ins Raster. Reicht die Breite fuer die Spalten nicht, rutschen die letzten nach unten (wie
        ``_optionskaesten_ordnen`` im Hauptfenster): Sonst ragte ein Haken aus der Karte, unsichtbar und nicht anklickbar."""
        haken = getattr(self, "nach_erfolg_haken", {})
        sichtbar = [n for n in self.HAKEN_REIHENFOLGE
                    if n in haken and (n != "ueberschreiben" or getattr(self, "_ueberschreiben_zeigen", True))]
        if not sichtbar:
            return
        try:
            spalten = self._haken_spalten(sichtbar, breite)
            ort = tuple(tuple(s) for s in spalten)
            if ort == getattr(self, "_haken_ort", None):
                return
            self._haken_ort = ort
            for name, h in haken.items():
                if name not in sichtbar:
                    h.grid_remove()
            for spalte, namen in enumerate(spalten):
                for zeile, name in enumerate(namen):
                    haken[name].grid(row=zeile, column=spalte, sticky="w", padx=(self.HAKEN_ABSTAND if spalte else 0, 0),
                                     pady=(6 if zeile else 0, 0))
        except tk.TclError as exc:
            logger.debug("Haken nicht anordenbar: %s", exc)

    def _loeschen_vorbereiten(self, art: str, info: "wz.PaketInfo") -> "tuple[bool, dict | None]":
        """Fragt vor dem Start, ob die Quelle nach Erfolg geloescht wird (``_quelle_loeschen_bestaetigen`` der Aufgaben 1 bis 6).

        Returns:
            ``(False, None)``: nichts starten (Abbrechen). Sonst ``(True, None)`` ohne Loeschen oder ``(True, {"quelle", "stempel"})`` -
            der Stempel merkt, wie die Quelle jetzt aussieht: Wer sie waehrend des Laufs aendert, behaelt sie.
        """
        g = self.g
        gewaehlt = getattr(g, "_quelle_loeschen_gewaehlt", None)
        if art not in self.ERGEBNIS_ARTEN or not callable(gewaehlt) or not gewaehlt():
            return True, None
        antwort = g._quelle_loeschen_bestaetigen("pkg_fpkg", info.pfad)
        if antwort is None:
            return False, None
        if not antwort:
            return True, None
        quelle = g._quelle_zum_loeschen(info.pfad)
        return True, {"quelle": quelle, "stempel": quelle_loeschen.stempel_nehmen(quelle)}

    def _nach_erfolg(self, art: str, ergebnis: str, loeschen: "dict | None", befund: bool = False) -> None:
        """Hauptfaden, nach einem Auftrag, der gut ausgegangen ist: Quelle loeschen, Ergebnis senden, herunterfahren.

        Ein Befund der Pruefung zaehlt nicht als Erfolg: Dann bleibt die Quelle, nichts wird gesendet, der Rechner bleibt an.
        Das Loeschen laeuft im Faden (ein Spielordner braucht Sekunden bis Minuten); danach geht der Takt weiter
        (:meth:`_nach_erfolg_weiter`) - der Rechner faehrt nie mitten im Loeschen herunter.
        """
        if befund:
            return
        if loeschen and ergebnis:
            self._nachlauf = True
            threading.Thread(target=self._quelle_loeschen_lauf, args=(art, ergebnis, loeschen), daemon=True,
                             name="ps5pkg-loeschen").start()
            return
        self._nach_erfolg_weiter(art, ergebnis)

    def _quelle_loeschen_lauf(self, art: str, ergebnis: str, loeschen: dict) -> None:
        """Faden: loescht die Quelle, wenn alles stimmt (``quelle_loeschen.pruefen``); sonst bleibt sie, und das Protokoll sagt warum."""
        g = self.g
        quelle = loeschen["quelle"]
        try:
            grund = quelle_loeschen.pruefen(quelle, ergebnis, loeschen.get("stempel"))
            if grund:
                self._melden(g._t("log.quelle_bleibt", pfad=quelle, grund=g._t("quelle_loeschen.grund." + grund)))
            else:
                self._melden(g._t("log.quelle_wird_geloescht", pfad=quelle))
                haupt = _haupt(g)
                fehler = quelle_loeschen.loeschen(quelle, ordner_loeschen=lambda p: bool(haupt._rmtree_force(p)),
                                                  datei_loeschen=os.remove)
                self._melden(g._t("log.quelle_loeschen_fehler", pfad=quelle, fehler=fehler) if fehler
                             else g._t("log.quelle_geloescht", pfad=quelle))
        except Exception as exc:  # noqa: BLE001 - im Zweifel bleibt die Quelle
            logger.exception("Quelle loeschen")
            self._melden(g._t("log.quelle_loeschen_fehler", pfad=quelle, fehler=str(exc)))
        finally:
            with self._sperre:
                self._z["nachlauf"].append((art, ergebnis))

    def _nach_erfolg_weiter(self, art: str, ergebnis: str) -> None:
        """Erfolgsmeldung, Ergebnis an die PS5 senden (nur nach Rueckfrage, und nicht, wenn der Rechner herunterfaehrt - niemand wuerde
        antworten), danach herunterfahren - in der Reihenfolge der Aufgaben 1 bis 6. Ueber Aufgabe 1 (``umwandeln``) hat sie alles
        schon selbst erledigt."""
        g = self.g
        if art == "umwandeln":
            return
        herunterfahren = bool(getattr(g, "_shutdown_after_success_enabled", lambda: False)())
        if not herunterfahren and art in self.MELDUNG_ARTEN:
            self._erfolg_melden()
        senden = getattr(g, "_senden_nach_erfolg_enabled", None)
        if (not herunterfahren and ergebnis and art in ("bauen", "abbild", "extrahieren") and callable(senden) and senden()):
            self._senden_fragen(ergebnis)
        if herunterfahren:
            g._last_task_ok = True                 # ``_should_shutdown_after_task`` liest den Erfolg aus diesem Merker
            g._maybe_shutdown_after_task()

    def _erfolg_melden(self) -> None:
        """Dieselbe Meldung wie nach einem Lauf der Aufgaben 1 bis 6: Titel "Erfolg", Text "Vorgang erfolgreich abgeschlossen!".

        Beim Herunterfahren entfaellt sie (der Aufrufer prueft das): Sie wartete auf eine Bestaetigung, die niemand gibt - der Sinn
        des Hakens ist ja, den Rechner unbeaufsichtigt zu lassen. Der Erfolg steht dann in der Statuszeile und im Protokoll.
        """
        g = self.g
        messagebox.showinfo(g._t("dialog.title.success"), g._t("dialog.msg.task_completed_successfully"), parent=self.win)

    def _senden_fragen(self, ergebnis: str) -> None:
        """Dieselbe Rueckfrage wie nach einem Lauf der Aufgaben 1 bis 6 (``_nach_erfolg_senden_fragen``), dann Senden."""
        g = self.g
        name = os.path.basename(os.path.normpath(ergebnis))
        if not messagebox.askyesno(g._t("dialog.title.nach_erfolg_senden"), g._t("dialog.msg.nach_erfolg_senden_frage", name=name),
                                   parent=self.win):
            return
        g._nach_erfolg_senden_starten([ergebnis])

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
        if self._job is not None:
            # Der Arbeitsfaden haengt womoeglich im Lesen der Werkzeugausgabe - der Prozess muss sofort enden.
            wz.alle_beenden()
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
            *, master: "tk.Misc | None" = None, karte_bauer: "Callable | None" = None,
            quelle_bauer: "Callable | None" = None) -> Ps5PkgFenster:
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
    fenster = Ps5PkgFenster(gui, schrift, mono, pt, vorgabe, master=master, karte_bauer=karte_bauer,
                            quelle_bauer=quelle_bauer)
    setattr(gui, FENSTER_ATTRIBUT, fenster)
    return fenster
