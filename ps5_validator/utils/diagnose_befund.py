# -*- coding: utf-8 -*-
"""Der Diagnosebericht - die Teile, die keine Oberflaeche brauchen.

Elfter Schnitt der Trennung. Der Diagnoseblock hat 25 Methoden; etwa die
Haelfte davon vermisst Widgets - Randlosigkeit, Flaechen, Bilder,
Skalierung, Laufruhe. Die bleiben im Monolithen, wo sie hingehoeren.

Hier stehen die zwoelf, die ueber das **System** berichten statt ueber das
Fenster: Speicherplatz und Arbeitsspeicher, DPI-Bewusstsein, der Bestand
an mitgelieferten Werkzeugen, die Umgebung, die Protokolldatei - und die
Optimierungspruefung, mit 249 Zeilen die groesste.

**Die Werte kommen als Objekte mit ``.get()`` herein.** Im Monolithen
liest der Bericht Tk-Variablen (``self.temp_path.get()``). Dieses Modul
kennt Tk nicht; es ruft nur ``.get()``. Damit nimmt es sowohl eine
Tk-Variable als auch einen neutralen Wert aus
:mod:`ps5_validator.ui.zustand` - und die WPF-Fassung kann denselben
Bericht erzeugen.

**Die Programmwurzel kommt ebenfalls herein.** Der Bericht bildete sie
aus ``sys.argv[0]`` und ``__file__``; aus ``ps5_validator/utils/`` heraus
zeigt das woandershin. Es ist die vierte Stelle dieser Art in dieser
Sitzung.
"""
from __future__ import annotations

import ctypes
import datetime
import importlib
import io
import json
import logging
import os
import platform
import shutil
import sys
import tempfile
import time
from typing import Any, Callable

from ps5_validator.utils import darstellung
from ps5_validator.utils import einstellungen
from ps5_validator.utils.nahtstellen import (Textquelle,
                                             schluessel_zeigen)
from ps5_validator.utils.werkzeuge_bereitstellen import (
    UFS2TOOL_ORDNER)
from ps5_validator.utils.plattform import (IST_MACOS, IST_WINDOWS,
                                           ist_administrator)

logger = logging.getLogger("PS5Converter.utils.diagnose_befund")


class Diagnosebericht:
    """Sammelt die Befunde ueber das System.

    Args:
        programm_ordner: Der Ordner der Programmdatei.
        hauptdatei: Die Hauptdatei des Programms. Sie wird gemessen (ihre
            Groesse steht im Bericht) und ist der Ort, an dem
            ``coverage.json`` gesucht wird - beides waere mit dem
            ``__file__`` dieses Moduls falsch.
        quelle, ziel, temp: Werteobjekte mit ``.get()`` fuer die drei Pfade.
        kompression: Werteobjekt mit ``.get()`` fuer die Packstufe.
        einstellung_lesen, einstellung_schreiben: Zugriff auf die
            Einstellungsdatei.
        mitgeliefert_finden: Findet einen mitgelieferten Ordner.
        eingebettete_werkzeuge, gepruefte_bibliotheken,
            fremdwerkzeuge_quellen: Die drei Tabellen fuer den
            Werkzeugbestand. Sie bleiben im Monolithen stehen, weil
            Pruefungen sie an der Klasse lesen.
        eingebettete_fassung: Liest die Fassung eines mitgelieferten
            Werkzeugs.
        ampr_hoechste_fassung: Die hoechste mitgelieferte AMPR-Fassung.
        ufs2tool_plattform: Welcher UFS2Tool-Bau gilt.
        datei_fassung: Liest die Fassung einer fremden Programmdatei.
        eigenschaften_pruefen: Die Pruefung der Programmeigenschaften.
        bytes_formatieren: Formatiert eine Byte-Zahl lesbar.
        macos_translokation: Meldet, ob macOS das Programm verschoben hat.
        ampr_ordner, hintergrund_ordner: Namen der mitgelieferten Ordner.
        rueckschritt_ab_prozent: Ab wann ein Rueckschritt gemeldet wird.
        drag_and_drop: Ob tkinterdnd2 vorhanden ist.
        doktor: Die Umgebungspruefung (``umgebung_doktor``).
        mkpfs_ordner: Wohin die Engine entpackt wurde.
        letzte_dauer_s, quellbytes: Die Messwerte des letzten
            Laufs - aus ihnen rechnet der Bericht den Durchsatz.
        fortschritts_waechter: Der Waechter, falls einer laeuft.
    """

    def __init__(self, *, programm_ordner: str = "",
                 hauptdatei: str = "",
                 quelle: Any = None, ziel: Any = None, temp: Any = None,
                 kompression: Any = None,
                 einstellung_lesen: Callable[..., Any] | None = None,
                 einstellung_schreiben: Callable[..., Any] | None = None,
                 mitgeliefert_finden: Callable[..., Any] | None = None,
                 eingebettete_werkzeuge: tuple = (),
                 gepruefte_bibliotheken: tuple = (),
                 fremdwerkzeuge_quellen: dict | None = None,
                 eingebettete_fassung: Callable[..., Any] | None = None,
                 ampr_hoechste_fassung: Callable[..., Any] | None = None,
                 ufs2tool_plattform: Callable[..., Any] | None = None,
                 datei_fassung: Callable[..., Any] | None = None,
                 eigenschaften_pruefen: Callable[..., Any] | None = None,
                 bytes_formatieren: Callable[..., Any] | None = None,
                 macos_translokation: Callable[..., Any] | None = None,
                 ampr_ordner: str = "PlayGo & AMPR_EMU",
                 hintergrund_ordner: str = "Hintergrundbilder",
                 rueckschritt_ab_prozent: float = 5.0,
                 drag_and_drop: bool = False,
                 doktor: Callable[..., Any] | None = None,
                 mkpfs_ordner: str = "",
                 letzte_dauer_s: float = 0.0,
                 quellbytes: int = 0,
                 fortschritts_waechter: Any = None,
                 text: Textquelle | None = None,
                 aufgabe: Any = None,
                 anzeige_pruefen: Callable[..., Any] | None = None,
                 konfigpfad: Callable[[], str] | None = None,
                 schwaerzen_hinweise: tuple = (),
                 bauer_holen: Callable[[str], Any] | None = None,
                 protokollschwanz: Callable[[], list] | None = None,
                 fassung: str = "",
                 letzte_fehler: Any = None) -> None:
        self._programm_ordner = programm_ordner or os.getcwd()
        self._hauptdatei = hauptdatei or __file__
        self.source_path = quelle
        self.dest_path = ziel
        self.temp_path = temp
        self.compression_level_var = kompression
        self._load_setting = einstellung_lesen or (lambda *a, **k: "")
        self._save_setting = einstellung_schreiben or (lambda *a, **k: None)
        self._mitgeliefert_finden = mitgeliefert_finden or (lambda *a: "")
        self._EINGEBETTETE_WERKZEUGE = eingebettete_werkzeuge
        self._GEPRUEFTE_BIBLIOTHEKEN = gepruefte_bibliotheken
        self._FREMDWERKZEUGE_QUELLEN = fremdwerkzeuge_quellen or {}
        self._eingebettete_fassung = eingebettete_fassung or (lambda *a: "")
        self._ampr_hoechste_fassung = ampr_hoechste_fassung or (lambda: "")
        self._ufs2tool_plattform = ufs2tool_plattform or (lambda: "")
        self._datei_fassung = datei_fassung or (lambda *a: "")
        self._eigenschaften_pruefen = eigenschaften_pruefen or (lambda *a: [])
        # Ohne Rueckruf die echte Umrechnung, nicht die nackte Zahl:
        # Sonst stehen im Bericht Bytezahlen wie 587202560, und das
        # faellt niemandem auf - es sieht nur unfertig aus.
        self._fmt_bytes = bytes_formatieren or darstellung.bytes_lesbar
        self._macos_translokation = macos_translokation or (lambda: None)
        self._AMPR_BUNDLED_STORE_DIR = ampr_ordner
        self._BACKGROUND_BUNDLED_DIR = hintergrund_ordner
        self._RUECKSCHRITT_AB_PROZENT = rueckschritt_ab_prozent
        self._DND_AVAILABLE = drag_and_drop
        self._umgebung_doktor = doktor or (lambda *a, **k: [])
        # Vier Werte, die der Bericht ueber getattr liest - sie
        # kommen aus dem letzten Lauf und fehlen beim ersten Start.
        self.mkpfs_dir = mkpfs_ordner
        self._letzte_aufgabe_dauer_s = letzte_dauer_s
        self.task_total_source_bytes = quellbytes
        self.fortschritts_waechter = fortschritts_waechter
        self._t = text or schluessel_zeigen
        self.current_mode = aufgabe
        self._diagnose_pruefen = anzeige_pruefen or (lambda: [])
        # Ueber den Rueckruf, nie ueber einstellungen.pfad(): Wer
        # _get_config_path ersetzt, muss hier durchdringen.
        self._get_config_path = konfigpfad or einstellungen.pfad
        self._DIAGNOSTIC_REDACT_KEY_HINTS = schwaerzen_hinweise
        # Alle elf Abschnittsbauer kommen ueber diesen einen Rueckruf -
        # auch die acht, die dieses Modul selbst besitzt. Sonst koennte
        # ein Traeger sie nicht ersetzen, und die Kette waere gekappt.
        self._bauer_holen = bauer_holen or (
            lambda name: getattr(self, name, None))
        # Als Rueckruf, nicht als Wert: _build_log_tail wird beim
        # Kuerzen neu zugewiesen, eine Referenz zeigte danach ins Leere.
        self._protokollschwanz = protokollschwanz or (lambda: [])
        self._fassung = fassung
        # Als Referenz, nicht als Kopie: _LETZTE_FEHLER ist eine deque,
        # die nur waechst - so bleibt der Bericht aktuell.
        self._letzte_fehler = ([] if letzte_fehler is None
                               else letzte_fehler)

    @staticmethod
    def _diagnose_zeile(name: str, wert) -> str:
        """Eine Zeile des Berichts - Werte bleiben sprachneutral."""
        return "%s: %s" % (name, wert)

    def _diagnose_umgebung(self) -> list[str]:
        """Wie das Programm laeuft und womit - die Kompatibilitaetsseite."""
        z = self._diagnose_zeile
        zeilen = [
            z("Gebaut als EXE", bool(getattr(sys, "frozen", False))),
            z("_MEIPASS", getattr(sys, "_MEIPASS", "-")),
            z("Programmpfad", os.path.abspath(sys.argv[0])),
            z("Arbeitsverzeichnis", os.getcwd()),
            z("Administratorrechte", ist_administrator()),
            z("macOS App Translocation", self._macos_translokation()),
        ]
        for name, modul in (("Pillow", "PIL"), ("tkinterdnd2", "tkinterdnd2"),
                            ("psutil", "psutil")):
            try:
                m = __import__(modul)
                zeilen.append(z(name, getattr(m, "__version__", "vorhanden")))
            except Exception:
                zeilen.append(z(name, "fehlt"))
        zeilen.append(z("Drag & Drop aktiv", self._DND_AVAILABLE))
        zeilen.append(z("mkpfs-Ordner", getattr(self, "mkpfs_dir", "") or "noch nicht entpackt"))
        return zeilen

    def _diagnose_werkzeuge(self) -> list[str]:
        """Die gemerkten Pfade der Fremdwerkzeuge.

        Bewusst nur die gespeicherten Angaben und eine Existenzpruefung: Ein
        frischer Suchlauf durchkaemmt im schlimmsten Fall alle Laufwerke, und
        ein Diagnosebericht darf nicht minutenlang haengen.
        """
        z = self._diagnose_zeile
        zeilen: list[str] = []
        # UFS2Tool steht seit v1.8.72 im Abschnitt der mitgelieferten
        # Werkzeuge - hier gehoert nur her, was der Nutzer selbst
        # installiert und das Programm suchen muss.
        for name, schluessel in (("FileZilla", "filezilla_path"),
                                 ("OSFMount", "osfmount_path")):
            try:
                pfad = str(self._load_setting(schluessel, "") or "").strip()
            except Exception:
                pfad = ""
            if not pfad:
                zeilen.append(z(name, "nicht gemerkt"))
            else:
                da = os.path.isfile(pfad) or (pfad.endswith(".app") and os.path.isdir(pfad))
                zeilen.append(z(name, "%s (%s)" % (pfad, "vorhanden" if da else "FEHLT")))
        return zeilen

    def _diagnose_speicherplatz(self) -> list[str]:
        """Freier Platz auf Quelle, Ziel und Temp - haeufigste Abbruchursache."""
        z = self._diagnose_zeile
        zeilen: list[str] = []
        gesehen: set[str] = set()
        for name, holen in (("Quelle", lambda: self.source_path.get()),
                            ("Ziel", lambda: self.dest_path.get()),
                            ("Temp", lambda: self.temp_path.get())):
            try:
                pfad = str(holen() or "").strip()
            except Exception:
                pfad = ""
            if not pfad:
                continue
            wurzel = os.path.splitdrive(os.path.abspath(pfad))[0] or "/"
            if wurzel in gesehen:
                continue
            gesehen.add(wurzel)
            try:
                _gesamt, _belegt, frei = shutil.disk_usage(pfad if os.path.exists(pfad) else wurzel)
                zeilen.append(z("%s (%s)" % (name, wurzel),
                                "%.1f GB frei" % (frei / 1024**3)))
            except Exception as exc:
                zeilen.append(z("%s (%s)" % (name, wurzel), "nicht ermittelbar: %s" % exc))
        return zeilen

    @staticmethod
    def _diagnose_speicher_mb() -> float:
        """Wie viel Arbeitsspeicher der eigene Prozess gerade belegt.

        Returns:
            Megabyte, oder 0.0 wenn es sich nicht ermitteln laesst.
        """
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1048576.0
        except Exception:
            pass
        if IST_WINDOWS:
            try:
                class _Zaehler(ctypes.Structure):
                    _fields_ = [("cb", ctypes.c_ulong),
                                ("PageFaultCount", ctypes.c_ulong),
                                ("PeakWorkingSetSize", ctypes.c_size_t),
                                ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                                ("PagefileUsage", ctypes.c_size_t),
                                ("PeakPagefileUsage", ctypes.c_size_t)]

                zaehler = _Zaehler()
                zaehler.cb = ctypes.sizeof(_Zaehler)
                if ctypes.windll.psapi.GetProcessMemoryInfo(
                        ctypes.windll.kernel32.GetCurrentProcess(),
                        ctypes.byref(zaehler), zaehler.cb):
                    return zaehler.WorkingSetSize / 1048576.0
            except Exception as exc:
                logger.debug("Speicher nicht auslesbar: %s", exc)
            return 0.0
        try:
            import resource
            roh = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux zaehlt in Kilobyte, macOS in Byte.
            return roh / (1048576.0 if IST_MACOS else 1024.0)
        except Exception as exc:
            logger.debug("Speicher nicht auslesbar: %s", exc)
        return 0.0

    def _diagnose_dpi_bewusstsein(self):
        """Was Windows ueber die DPI-Faehigkeit des Prozesses denkt.

        0 bedeutet: Der Prozess zeichnet in 96 dpi, und Windows zieht das
        fertige Fenster als Bitmap auf die echte Groesse hoch. Dann ist nicht
        ein Bild unscharf, sondern die ganze Oberflaeche.

        Returns:
            Die Stufe, oder ``None`` ausserhalb von Windows bzw. wenn die
            Abfrage fehlschlaegt.
        """
        if not IST_WINDOWS:
            return None
        try:
            stufe = ctypes.c_int(0)
            ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(stufe))
            return int(stufe.value)
        except Exception:
            pass
        try:
            # Aeltere Windows-Fassungen kennen nur diese Abfrage.
            return 1 if ctypes.windll.user32.IsProcessDPIAware() else 0
        except Exception as exc:
            logger.debug("DPI-Bewusstsein nicht auslesbar: %s", exc)
            return None

    def _bestandteile_sammeln(self) -> list:
        """Stellt zusammen, was das Programm mitbringt und benutzt.

        Returns:
            Eine Liste von ``Bestandteil`` - eingebettete Werkzeuge,
            Python-Bibliotheken und gefundene Fremdwerkzeuge.
        """
        from ps5_validator.utils import aktualisierungen as ak

        teile: list = []
        for name, datei, art, quelle in self._EINGEBETTETE_WERKZEUGE:
            fassung = self._eingebettete_fassung(datei) or "unbekannt"
            teile.append(ak.Bestandteil(name, fassung, art, quelle))

        for anzeigename, importname, paket in self._GEPRUEFTE_BIBLIOTHEKEN:
            try:
                modul = __import__(importname)
                fassung = str(getattr(modul, "__version__", "") or "vorhanden")
            except Exception:
                continue
            teile.append(ak.Bestandteil(anzeigename, fassung, ak.PYPI, paket))

        # AMPR EMU hat sehr wohl eine abfragbare Quelle - das Projekt liegt auf
        # GitHub und veroeffentlicht dort seine Fassungen. Verglichen wird die
        # hoechste mitgelieferte Nummer.
        hoechste = self._ampr_hoechste_fassung()
        if hoechste:
            teile.append(ak.Bestandteil("AMPR EMU", hoechste, ak.GITHUB,
                                        "drakmor/ampr_emu"))

        # UFS2Tool liegt seit v1.8.72 bei, statt vom Nutzer gesucht zu werden.
        # Die Fassung steht in pruefsummen.json neben den Bauten.
        try:
            liste = os.path.join(self._mitgeliefert_finden(UFS2TOOL_ORDNER),
                                 "pruefsummen.json")
            with io.open(liste, encoding="utf-8") as datei:
                angaben = json.load(datei)
            teile.append(ak.Bestandteil(
                "UFS2Tool (%s)" % (self._ufs2tool_plattform() or "?"),
                str(angaben.get("fassung") or "unbekannt"),
                ak.GITHUB, "SvenGDK/UFS2Tool"))
        except Exception as exc:
            logger.debug("UFS2Tool-Fassung nicht lesbar: %s", exc)

        for name, schluessel in (("FileZilla", "filezilla_path"),
                                 ("OSFMount", "osfmount_path")):
            try:
                pfad = str(self._load_setting(schluessel, "") or "").strip()
            except Exception:
                pfad = ""
            if not pfad:
                continue
            fassung = self._datei_fassung(pfad) or "gefunden"
            teile.append(ak.Bestandteil(
                name, fassung, ak.OHNE_QUELLE,
                self._FREMDWERKZEUGE_QUELLEN.get(schluessel, "")))
        return teile

    #: Die elf Abschnitte des Berichts, in dieser Reihenfolge.
    #:
    #: Jeder Eintrag ist (Meldungsschluessel, Name des Bauers). Die
    #: Bauer werden ueber ``_bauer_holen`` geholt, nicht unmittelbar
    #: ueber ``self`` - so kann ein Traeger sie ersetzen.
    ABSCHNITTE = (
        ("diagnostics.report_section_display", "_diagnose_anzeige"),
        ("diagnostics.report_section_layout", "_diagnose_darstellung"),
        ("diagnostics.report_section_stability", "_diagnose_laufruhe"),
        ("diagnostics.report_section_progress", "_diagnose_fortschritt"),
        ("diagnostics.report_section_checks", "_diagnose_fachpruefungen"),
        ("diagnostics.report_section_optimization", "_diagnose_optimierung"),
        ("diagnostics.report_section_doctor", "_diagnose_doktor"),
        ("diagnostics.report_section_runtime", "_diagnose_umgebung"),
        ("diagnostics.report_section_inventory", "_diagnose_werkzeugbestand"),
        ("diagnostics.report_section_tools", "_diagnose_werkzeuge"),
        ("diagnostics.report_section_space", "_diagnose_speicherplatz"),
    )

    def bericht_text(self) -> str:
        """Baut den vollstaendigen Diagnose-Berichtstext zusammen.

        Kein Abschnitt darf den Bericht verhindern: Er ist genau dann
        gefragt, wenn etwas nicht stimmt. Was scheitert, wird als
        Zeile vermerkt, und der Rest wird trotzdem gebaut.
        """
        lines: list[str] = []
        lines.append(self._t("diagnostics.report_title"))
        lines.append(self._t(
            "diagnostics.report_created",
            timestamp=datetime.datetime.now().isoformat(timespec="seconds")))
        lines.append(self._t("diagnostics.report_version",
                             version=self._fassung))
        try:
            from ps5_validator.utils import anzeige_diagnose as _ad
            lines.append(_ad.zusammenfassung(self._diagnose_pruefen()))
        except Exception as exc:
            lines.append("Darstellung nicht pruefbar: %s" % exc)
        lines.append("")
        lines.append(self._t("diagnostics.report_section_system"))
        lines.append(self._t("diagnostics.report_os", os=platform.platform()))
        lines.append(self._t("diagnostics.report_python",
                             version=platform.python_version(),
                             arch=platform.architecture()[0]))
        lines.append(self._t(
            "diagnostics.report_cpu",
            cpu=platform.processor()
            or self._t("diagnostics.report_unknown")))
        lines.append("")
        lines.append(self._t("diagnostics.report_section_current_task"))
        lines.append(self._t("diagnostics.report_task",
                             task=self._wert_oder_strich("current_mode")))
        lines.append(self._t("diagnostics.report_source",
                             source=self._wert_oder_strich("source_path")))
        lines.append(self._t("diagnostics.report_target",
                             target=self._wert_oder_strich("dest_path")))
        lines.append("")
        lines.append(self._t("diagnostics.report_section_settings"))
        try:
            cfg_path = self._get_config_path()
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                for key, value in cfg.items():
                    if any(hint in key.lower()
                           for hint in self._DIAGNOSTIC_REDACT_KEY_HINTS):
                        value = self._t("diagnostics.report_redacted")
                    lines.append(f"{key}: {value}")
            else:
                lines.append(self._t("diagnostics.report_no_config"))
        except Exception as exc:
            lines.append(self._t("diagnostics.report_settings_read_failed",
                                 error=exc))

        for schluessel, name in self.ABSCHNITTE:
            lines.append("")
            lines.append(self._t(schluessel))
            try:
                bauer = self._bauer_holen(name)
                if bauer is None:
                    continue
                lines.extend(bauer())
            except Exception as exc:
                # Ein Abschnitt darf den Bericht nie verhindern - er ist
                # genau dann gefragt, wenn etwas nicht stimmt.
                lines.append("Abschnitt fehlgeschlagen: %s" % exc)

        lines.append("")
        lines.append(self._t("diagnostics.report_section_errors"))
        if self._letzte_fehler:
            for eintrag in self._letzte_fehler:
                lines.append(eintrag)
                lines.append("")
        else:
            lines.append(self._t("diagnostics.report_no_errors"))

        lines.append("")
        lines.append(self._t("diagnostics.report_section_logfile"))
        lines.extend(self._diagnose_protokolldatei())

        lines.append("")
        lines.append(self._t("diagnostics.report_section_log_tail"))
        tail = self._protokollschwanz() or []
        if tail:
            lines.extend(tail)
        else:
            lines.append(self._t("diagnostics.report_no_log"))
        return "\n".join(lines) + "\n"

    def _wert_oder_strich(self, name: str) -> str:
        """Liest ein Werteobjekt mit .get(), sonst einen Gedankenstrich.

        Die drei Pfadwerte kommen aus der Oberflaeche und fehlen, wenn
        der Bericht ohne sie gebaut wird - etwa auf der Konsole.
        """
        feld = getattr(self, name, None)
        if feld is None:
            return "–"
        try:
            return str(feld.get())
        except Exception:
            return "–"

    def _diagnose_werkzeugbestand(self) -> list[str]:
        """Was mitgeliefert wird - ohne Netz, in jedem Bericht.

        Returns:
            Die Zeilen des Berichtsabschnitts.
        """
        z = self._diagnose_zeile
        zeilen: list[str] = []
        for teil in self._bestandteile_sammeln():
            wo = ("  [%s]" % teil.quelle) if teil.quelle else ""
            zeilen.append(z(teil.name, "%s%s" % (teil.fassung, wo)))

        # Die Bestaende, die als Ordner mitkommen: Zahl und neueste Fassung
        # sagen mehr als eine Liste von zwanzig Namen.
        for name, ordner, muster in (
                ("AMPR-EMU-Bibliotheken", os.path.join("PlayGo & AMPR_EMU", "AMPR_EMU"), None),
                ("Backport-Fakelibs", "Backport_Fakelibs", None),
                ("Nutzlasten (helloworld)", "helloworld", ".elf")):
            pfad = self._mitgeliefert_finden(ordner)
            try:
                if not os.path.isdir(pfad):
                    zeilen.append(z(name, "nicht mitgeliefert"))
                    continue
                eintraege = sorted(os.listdir(pfad))
                if muster:
                    eintraege = [e for e in eintraege if e.lower().endswith(muster)]
                zeilen.append(z(name, "%d (%s)" % (
                    len(eintraege),
                    ", ".join(eintraege[:2]) + (" ..." if len(eintraege) > 2 else ""))))
            except Exception as exc:
                zeilen.append(z(name, "nicht lesbar: %s" % exc))
        return zeilen

    def _diagnose_eigenschaften(self) -> list[str]:
        """Prueft Zusicherungen, die immer gelten muessen - im fertigen Programm.

        Das Gegenstueck zu Hypothesis. Dort sucht eine Bibliothek selbst nach
        einer Eingabe, die eine Eigenschaft verletzt, und schrumpft sie auf
        das kleinste Gegenbeispiel (``test_eigenschaften.py``). Hier laeuft
        eine feste, kurze Auswahl derselben Eigenschaften - dafuer dort, wo
        kein Testlauf hinkommt: in der ausgelieferten EXE.

        Das ersetzt die Testdatei nicht und soll es nicht. Es faengt die
        Klasse Fehler, die erst durch das Verpacken entsteht: ein Modul, das
        PyInstaller nicht mitgenommen hat, eine andere Fassung einer
        Bibliothek, ein anderes Gebietsschema beim Umwandeln von Zahlen.

        Der Anlass: Am 25.08.2026 fand Hypothesis, dass ein einzelner
        Doppelpunkt in ``task_displayed`` die gesamte Fortschrittsschleife
        beendet - lautlos, ohne Absturz und ohne Meldung. Der Balken waere
        einfach stehengeblieben.
        """
        # Absichtlich unsinnige Bytes an ``parse_sfo`` erzeugen jedes Mal
        # eine Warnung. Beim ersten Lauf standen dadurch vier Meldungen im
        # Protokollauszug desselben Berichts - Rauschen, das der Diagnose
        # genau das nimmt, wofuer sie da ist. Waehrend der Pruefung bleibt
        # das Protokoll deshalb still - aber nur bis einschliesslich
        # WARNING. Echte Fehler aus einer nebenher laufenden
        # Konvertierung muessen weiter durchkommen.
        logging.disable(logging.WARNING)
        try:
            return self._eigenschaften_pruefen()
        finally:
            logging.disable(logging.NOTSET)

    def _diagnose_doktor(self) -> list[str]:
        """Die Umgebungspruefung mit den Pfaden dieser Sitzung."""
        try:
            temp = self.temp_path.get()
        except Exception:
            temp = ""
        try:
            ziel = self.dest_path.get()
        except Exception:
            ziel = ""
        return self._umgebung_doktor(temp, ziel)

    def _diagnose_optimierung(self) -> list[str]:
        """Die Optimierungsseite: Geschwindigkeit, Groesse, Abhaengigkeiten.

        Die Regel dahinter lautet: erst messen, dann optimieren. Deshalb
        steht hier keine Empfehlung ohne Zahl dahinter.

        Der Rueckschrittalarm ist das, was in einer Baukette ein
        Benchmark-Waechter tut: Er merkt sich die beste je gemessene
        Geschwindigkeit je Kompressionsstufe und schlaegt an, wenn ein Lauf
        deutlich darunter bleibt. Ohne diesen Vergleich faellt ein
        schleichender Verlust nicht auf - eine Aufgabe, die frueher 30 s
        brauchte und jetzt 45 s, fuehlt sich beim Zusehen gleich an.

        Am Ende steht ausdruecklich, was bei diesem Programm nicht greift.
        Sonst wird immer wieder danach gesucht.
        """
        zeilen: list[str] = []

        # -- Geschwindigkeit und Rueckschrittalarm ------------------------
        dauer = float(getattr(self, "_letzte_aufgabe_dauer_s", 0.0) or 0.0)
        quellbytes = int(getattr(self, "task_total_source_bytes", 0) or 0)
        try:
            stufe = str(self.compression_level_var.get() or "").strip()
        except Exception:
            stufe = ""
        if dauer > 0.0 and quellbytes > 0:
            durchsatz = quellbytes / dauer / 1048576.0
            schluessel = "opt_durchsatz_%s" % (stufe or "unbekannt")
            try:
                bestwert = float(self._load_setting(schluessel, 0.0) or 0.0)
            except (TypeError, ValueError):
                bestwert = 0.0
            zeilen.append("Durchsatz: %.1f MB/s (%s in %.1f s, Stufe %s)"
                          % (durchsatz, self._fmt_bytes(quellbytes), dauer,
                             stufe or "unbekannt"))
            if bestwert <= 0.0:
                zeilen.append("  erster Messwert dieser Stufe - ab jetzt der "
                              "Vergleichswert")
            else:
                abfall = (bestwert - durchsatz) / bestwert * 100.0
                zeilen.append("  bester Lauf bisher: %.1f MB/s (%+.0f %%)"
                              % (bestwert, -abfall))
                if abfall >= self._RUECKSCHRITT_AB_PROZENT:
                    zeilen.append("  ACHTUNG: %.0f %% langsamer als der beste "
                                  "Lauf - das ist mehr als Messrauschen."
                                  % abfall)
            if durchsatz > bestwert:
                try:
                    self._save_setting(schluessel, round(durchsatz, 2))
                except Exception:
                    pass
        else:
            zeilen.append("Durchsatz: seit dem Start lief keine Aufgabe")

        # -- Wohin die Groesse geht ---------------------------------------
        #
        # Das Gegenstueck zu Bloaty: Wohin geht die Groesse? Bei diesem
        # Bau in drei Toepfe - die Hintergrundbilder, die AMPR-/PlayGo-
        # Versionen und alles Uebrige. In v1.8.94 lagen die ersten beiden
        # neben der EXE; seit v1.8.95 stecken sie wieder darin, damit die
        # Auslieferung eine einzige Datei bleibt.
        def _ordnergroesse(pfad):
            gesamt, anzahl = 0, 0
            try:
                for wurzel, _unter, dateien in os.walk(pfad):
                    for name in dateien:
                        try:
                            gesamt += os.path.getsize(os.path.join(wurzel, name))
                            anzahl += 1
                        except OSError:
                            pass
            except OSError:
                pass
            return gesamt, anzahl

        # ``sys.argv[0]`` waere falsch: Beim Aufruf aus einem Skript heraus
        # stand dort das Skript (1,9 KB) statt des Programms.
        eigen_pfad = sys.executable if getattr(sys, "frozen", False) else self._hauptdatei
        try:
            eigen = os.path.getsize(os.path.abspath(eigen_pfad))
        except (OSError, NameError):
            eigen = 0
        if eigen:
            zeilen.append("Größe: %s %s"
                          % ("EXE" if getattr(sys, "frozen", False) else "Quelltext",
                             self._fmt_bytes(eigen)))
        # Beide Ordner stecken in der Programmdatei; die Zahlen sagen, wie
        # viel von ihrer Groesse auf sie entfaellt. Aus dem Quelltext
        # heraus waere "davon" falsch - dort ist noch nichts eingebettet,
        # und 43,6 MB Bilder "von" 3,9 MB Quelltext ergaeben Unsinn.
        eingebaut = bool(getattr(sys, "frozen", False))
        vorsatz = "davon " if eingebaut else ""
        nachsatz = "" if eingebaut else " (wird eingebettet)"
        for beschriftung, ordner in (
                ("Hintergrundbilder", self._BACKGROUND_BUNDLED_DIR),
                ("AMPR EMU + PlayGo", self._AMPR_BUNDLED_STORE_DIR)):
            pfad = self._mitgeliefert_finden(ordner)
            if not pfad:
                zeilen.append("  %s: nicht gefunden" % beschriftung)
                continue
            gross, anzahl = _ordnergroesse(pfad)
            zeilen.append("  %s%s%s: %s in %d Dateien"
                          % (vorsatz, beschriftung, nachsatz,
                             self._fmt_bytes(gross), anzahl))

        # -- Abhaengigkeiten, bei denen die Fassung die Zeit aendert ------
        #
        # Nur diese vier. Alles Uebrige steht im Abschnitt Laufzeitumgebung
        # und aendert an der Geschwindigkeit nichts.
        teile = []
        for name, modul, feld in (("zlib", "zlib", "ZLIB_RUNTIME_VERSION"),
                                  ("zstandard", "zstandard", "__version__"),
                                  ("Pillow", "PIL", "__version__"),
                                  ("cryptography", "cryptography", "__version__")):
            try:
                m = importlib.import_module(modul)
                teile.append("%s %s" % (name, getattr(m, feld, "vorhanden")))
            except Exception:
                teile.append("%s fehlt" % name)
        zeilen.append("Rechenbibliotheken: %s" % ", ".join(teile))

        # -- Womit sich nachmessen laesst ---------------------------------
        #
        # In der EXE fehlen diese alle, und das ist richtig so: Sie gehoeren
        # zur Entwicklung, nicht zur Auslieferung. Die Zeile ist dann nur
        # eine Feststellung, kein Mangel.
        # ``import importlib`` allein bringt das Untermodul nicht mit.
        import importlib.util as _ilu
        werkzeuge = []
        for name, art, ziel in (("ruff", "befehl", "ruff"),
                                ("py-spy", "befehl", "py-spy"),
                                ("hypothesis", "modul", "hypothesis"),
                                ("coverage", "modul", "coverage")):
            try:
                if art == "befehl":
                    # ``which`` sucht nur im PATH. Wird der Interpreter aus
                    # einer virtuellen Umgebung heraus direkt aufgerufen,
                    # steht deren Skriptordner dort nicht drin - ruff und
                    # coverage galten deshalb als fehlend, obwohl sie
                    # danebenlagen.
                    da = bool(shutil.which(ziel))
                    if not da:
                        neben = os.path.dirname(sys.executable)
                        da = any(os.path.isfile(os.path.join(neben, ziel + e))
                                 for e in ("", ".exe", ".cmd"))
                else:
                    da = _ilu.find_spec(ziel) is not None
            except Exception:
                da = False
            werkzeuge.append("%s %s" % (name, "da" if da else "fehlt"))
        zeilen.append("Messwerkzeuge: %s" % ", ".join(werkzeuge))

        # -- Testabdeckung ------------------------------------------------
        #
        # Sie hier zu messen ginge nicht: Dazu muesste die gesamte Testreihe
        # laufen, und das dauert Minuten. Gelesen wird deshalb das Ergebnis
        # des letzten Laufs. Steht dort ein altes Datum, ist die Zahl nicht
        # falsch, sondern nur von damals - und das steht dann auch da.
        abdeckung = os.path.join(os.path.dirname(os.path.abspath(
            self._hauptdatei if not getattr(sys, "frozen", False) else sys.executable)),
            "coverage.json")
        if os.path.isfile(abdeckung):
            try:
                with open(abdeckung, "r", encoding="utf-8") as f:
                    daten = json.load(f)
                gesamt = daten.get("totals", {})
                anteil = float(gesamt.get("percent_covered", 0.0))
                fehlend = int(gesamt.get("missing_lines", 0))
                alter_tage = (time.time() - os.path.getmtime(abdeckung)) / 86400.0
                zeilen.append("Testabdeckung: %.1f %% (%d Zeilen ungeprüft, "
                              "gemessen vor %.1f Tagen)"
                              % (anteil, fehlend, alter_tage))
            except (OSError, ValueError, KeyError) as exc:
                zeilen.append("Testabdeckung: coverage.json unlesbar (%s)"
                              % type(exc).__name__)
        else:
            zeilen.append("Testabdeckung: noch nicht gemessen "
                          "(coverage json -o coverage.json)")
        if not getattr(sys, "frozen", False):
            zeilen.append("  ruff check --fix .")
            zeilen.append("  coverage run -m unittest discover -p \"test_*.py\"")
            zeilen.append("  python -m unittest test_eigenschaften")
            zeilen.append("  python tools\\mutationstest.py"
                          "        (sind die Tests etwas wert?)")
            zeilen.append("  git bisect run powershell -NoProfile -File "
                          "tools\\bisect_prüfung.ps1 <testdatei>")

        # -- Was hier nicht greift, und warum -----------------------------
        zeilen.append("Nicht anwendbar auf dieses Programm:")
        zeilen.append("  PGO, LTO, BOLT, Propeller - betreffen den "
                      "Interpreter, nicht diesen Quelltext.")
        zeilen.append("    Die Bauten von python.org sind bereits mit PGO und "
                      "LTO übersetzt.")
        zeilen.append("  ccache, Ninja, mold, lld - hier wird nichts "
                      "übersetzt, nur verpackt.")
        zeilen.append("  Compiler Explorer - das Gegenstück heißt hier "
                      "dis.dis().")
        zeilen.append("  jemalloc, mimalloc, tcmalloc - CPython bringt "
                      "pymalloc mit und tauscht ihn nicht aus.")
        zeilen.append("  EXPLAIN ANALYZE, pgBadger, N+1-Suchen - es gibt "
                      "keine Datenbank, nur JSON-Dateien.")
        zeilen.append("  Lighthouse, Bundle-Analyzer, Brotli - es gibt keine "
                      "Webanwendung.")
        zeilen.append("  k6, Locust, Jäger, OpenTelemetry - ein Prozess auf "
                      "einem Rechner, kein Dienst,")
        zeilen.append("    keine verteilte Kette. Der Ersatz ist der "
                      "Stapelabzug im Abschnitt Fachprüfungen.")
        zeilen.append("  basisu, astcenc, meshoptimizer, RGA - es wird nichts "
                      "gerendert.")
        zeilen.append("  strace, ltrace, eBPF, bpftrace, DTrace - Linux- und "
                      "BSD-Kernwerkzeuge.")
        zeilen.append("    Unter Windows wäre Process Monitor das "
                      "Gegenstück; er ist nicht eingebaut,")
        zeilen.append("    sondern von Hand zu starten, wenn eine Datei "
                      "oder ein Schlüssel fehlt.")
        zeilen.append("  Wireshark, mitmproxy, Burp - es gibt eine einzige "
                      "Verbindung: FTP zur eigenen")
        zeilen.append("    Konsole im Heimnetz, unverschlüsselt und ohne "
                      "Anmeldedaten. Nichts zu entschlüsseln.")
        zeilen.append("  Ghidra, IDA, x64dbg, objdump - es entsteht kein "
                      "Maschinencode aus diesem Quelltext.")
        zeilen.append("  Jepsen, loom, Antithesis - ein Prozess auf einem "
                      "Rechner, keine verteilte Datenbank.")
        zeilen.append("  TLA+, Dafny, Z3 - lohnen, wo ein Fehler richtig "
                      "teuer ist. Dieselbe Fehlerklasse")
        zeilen.append("    fängt hier Hypothesis, und zwar erheblich "
                      "billiger.")
        zeilen.append("  Pact, Schemathesis, WireMock - es gibt keine "
                      "Schnittstelle zwischen zwei Diensten.")
        zeilen.append("  Feature Flags, Canary, Blue/Green - ausgeliefert "
                      "wird eine Datei, nicht ein Dienst.")

        # -- Anwendbar, aber von Hand --------------------------------------
        #
        # Diese drei gehoeren nicht in einen Bericht, der bei jedem Oeffnen
        # entsteht: Zwei brauchen das Netz, einer braucht Minuten.
        zeilen.append("Anwendbar, aber nicht eingebaut (bewusst):")
        zeilen.append("  gitleaks / trufflehog - suchen versehentlich "
                      "eingecheckte Zugangsdaten.")
        zeilen.append("    Im Bericht selbst werden sie bereits geschwärzt "
                      "(siehe Einstellungen oben).")
        zeilen.append("  syft + grype - Stückliste und CVE-Abgleich; "
                      "braucht eine Datenbank aus dem Netz.")
        zeilen.append("  Reproducible Builds - zweimal bauen und die "
                      "Prüfsummen vergleichen.")
        zeilen.append("    Ungemessen: PyInstaller schreibt Zeitstempel mit, "
                      "bitgleich wird es vermutlich nicht.")

        return zeilen

    def _diagnose_fortschritt(self) -> list[str]:
        """Was die Fortschrittsanzeige waehrend der letzten Aufgabe zeigte.

        Gemessen wird nicht, was der Code aufruft, sondern was im Fenster
        steht - Balken, Prozentzahl und Statuszeile, bei jedem Takt. Genau
        so wurden am 24.08.2026 zwei Fehler im exFAT-Weg gefunden, die
        vorher niemandem aufgefallen waren.
        """
        waechter = getattr(self, "fortschritts_waechter", None)
        if waechter is None:
            return ["(kein Wächter vorhanden)"]
        return waechter.bericht()

    @staticmethod
    def _diagnose_protokolldatei(zeilen_anzahl: int = 80) -> list[str]:
        """Die letzten Zeilen aus ps5converter.log im TEMP-Ordner.

        Das Konsolenfenster haelt nur 60 Zeilen des laufenden Baus. Die
        Protokolldatei reicht weiter zurueck und enthaelt insbesondere die
        Rueckverfolgungen der abgefangenen Ausnahmen.
        """
        try:
            pfad = os.path.join(tempfile.gettempdir(), "ps5converter.log")
            if not os.path.isfile(pfad):
                return ["(%s gibt es nicht)" % pfad]

            # Die Groesse gehoert in den Bericht. Am 23.08.2026 lag hier eine
            # Datei mit 22 MB und 322.195 Zeilen - nichts begrenzte sie, und
            # der Bericht zeigte davon nur die letzten achtzig, ohne zu
            # verraten, dass darunter zwei Wochen lagen.
            groesse = os.path.getsize(pfad)
            if groesse >= 1024 * 1024:
                mass = "%.1f MB" % (groesse / (1024 * 1024))
            else:
                mass = "%d KB" % (groesse // 1024)
            kopf = ["(%s, %s)" % (pfad, mass)]

            # Nur das Ende lesen. Vorher ging die vollstaendige Datei in den
            # Speicher, um achtzig Zeilen daraus zu zeigen.
            schwanz = 256 * 1024
            with io.open(pfad, "rb") as datei:
                if groesse > schwanz:
                    datei.seek(groesse - schwanz)
                    datei.readline()          # angebrochene Zeile verwerfen
                block = datei.read()
            alle = block.decode("utf-8", errors="replace").splitlines()
            return kopf + (alle[-zeilen_anzahl:] or ["(leer)"])
        except Exception as exc:
            return ["Protokolldatei nicht lesbar: %s" % exc]
#: Wie viele Diagnoseberichte im Ordner bleiben.
#:
#: Zehn sind genug: Wer einen Bericht weitergeben will, tut das gleich;
#: wer vergleichen will, braucht die letzten paar. Was aelter ist, hat
#: noch nie jemand gebraucht.
BERICHTE_BEHALTEN: int = 10


def alte_berichte_aufraeumen(ordner: str,
                             behalten: int = BERICHTE_BEHALTEN) -> int:
    """Loescht alle bis auf die juengsten Berichte. Gibt die Zahl zurueck.

    Sortiert wird ueber den Dateinamen - der traegt den Zeitstempel im
    Format JJJJMMTT_HHMMSS und ist damit von selbst in der richtigen
    Reihenfolge. Das Aenderungsdatum waere unzuverlaessig: Ein Kopieren
    des Ordners setzt es neu.

    Faellt ein Loeschen aus, ist das kein Grund, den Bericht nicht zu
    zeigen - er ist ja gerade dann gefragt, wenn etwas klemmt.

    Args:
        ordner: Wo die Berichte liegen. Leer heisst: nichts tun.
        behalten: Wie viele die juengsten bleiben.

    Returns:
        Wie viele Dateien entfernt wurden.
    """
    # Ohne Ordner wird nichts angefasst. os.listdir("") nimmt sonst je
    # nach System das Arbeitsverzeichnis - und dieser Weg loescht.
    if not ordner:
        return 0
    try:
        namen = sorted(n for n in os.listdir(ordner)
                       if n.startswith("Diagnosebericht_")
                       and n.endswith(".txt"))
    except OSError as exc:
        logger.debug("Berichte nicht auflistbar: %s", exc)
        return 0
    ueberzaehlig = namen[:-behalten] if behalten > 0 else []
    entfernt = 0
    for name in ueberzaehlig:
        try:
            os.remove(os.path.join(ordner, name))
            entfernt += 1
        except OSError as exc:
            logger.debug("Bericht %s nicht loeschbar: %s", name, exc)
    if entfernt:
        logger.info("%d alte Diagnoseberichte entfernt, %d behalten",
                    entfernt, len(namen) - entfernt)
    return entfernt
