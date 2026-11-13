# -*- coding: utf-8 -*-
"""Die Betriebspruefung: was im laufenden Programm schiefgegangen ist oder gleich schiefgeht.

``anzeige_diagnose`` prueft, wie das Fenster aussieht. Dieses Modul prueft, **wie es dem Programm geht**: Fehler im
Protokoll, liegen gebliebene Arbeitsordner, verwaiste Werkzeug-Prozesse, knapp werdende Windows-Ressourcen, angehaltene
Wiederaufnahmepunkte, fehlende Uebersetzungen und das, was der Doktor und die Werkzeugpflege schon melden, bisher aber
nirgends zaehlte.

Anlass (03.11.2026): Der Diagnosebericht sagte oben "Darstellung: keine Auffaelligkeit", obwohl weiter unten ein
``ERROR`` mit Rueckverfolgung im Protokoll stand, der OSFMount-Treiber fehlte und kein Administratorrecht da war.
Dasselbe Muster wie bei den Fehlern der Aufgabe 7 (Balken auf 100 %, Werkzeug lief nach dem Schliessen weiter): Die
Anzeichen waren da, nur las sie niemand zusammen. Jetzt gibt es **ein** Gesamturteil und eine Rueckgabe fuer
``--anzeige-diagnose``.

Aufbau wie ``anzeige_diagnose``: Je Bereich eine kleine ``*lage``-Datenklasse, eine ``pruefe_*``-Funktion, die daraus
``Befund``-Objekte macht (rein, ohne Platte und ohne Tk), und eine ``*_messen``-Funktion, die die Lage am echten
Rechner liest. Texte der Befunde sind deutsch, wie dort; nur die Kopfzeilen kommen uebersetzt von aussen.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from ps5_validator.utils.anzeige_diagnose import (
    FEHLER, HINWEIS, WARNUNG, Befund, Pruefergebnis)

# ---------------------------------------------------------------------------
# Grenzen
# ---------------------------------------------------------------------------
#: Fehler im Protokoll zaehlen, solange sie nicht aelter sind.
PROTOKOLL_FRIST_H = 24
#: Wie viel vom Ende der Protokolldatei gelesen wird.
PROTOKOLL_SCHWANZ_BYTES = 1024 * 1024
#: So viele verschiedene Fehler/Warnungen werden einzeln genannt, der Rest wird gezaehlt.
PROTOKOLL_GRUPPEN_MAX = 5

#: Ein Arbeitsordner, der juenger ist, gehoert vielleicht zu einem Lauf, der gerade anlaeuft.
RESTE_MINDESTALTER_S = 600
#: Hoechstens so lange darf das Vermessen der Reste dauern.
RESTE_ZEITBUDGET_S = 3.0
RESTE_MAX_NENNUNGEN = 6

#: Windows kennt je Prozess hoechstens 10 000 GDI- und 10 000 USER-Objekte (Standard).
GDI_WARNUNG, GDI_FEHLER = 7000, 9000
USER_WARNUNG, USER_FEHLER = 7000, 9000
HANDLES_WARNUNG, HANDLES_FEHLER = 8000, 15000
FADEN_WARNUNG, FADEN_FEHLER = 60, 150

#: Wiederaufnahmepunkte, die so lange unfertig liegen, werden nie fortgesetzt.
WIEDERAUFNAHME_ALT_TAGE = 14

#: Prozessnamen (kleingeschrieben, ohne ``.exe``), die dieses Programm als Werkzeug startet.
WERKZEUG_PROZESSE = ("orbispkgtool", "ffpfsc-pkg-tool", "prosperopkgtool", "ps5pkgtool", "ufs2tool", "mkpfs",
                     "robocopy", "7z", "7za", "makefs", "newfs")

# Marken der Doktor-Zeilen (siehe ``umgebung_doktor`` im Hauptmodul).
DOKTOR_HINWEIS = "[ !! ]"
DOKTOR_FEHLER = "[FEHL]"


# ---------------------------------------------------------------------------
# Protokoll
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LogEintrag:
    """Ein Eintrag der Protokolldatei samt seiner Folgezeilen (Rueckverfolgung)."""

    zeit: datetime.datetime | None
    stufe: str
    text: str
    rueckverfolgung: bool = False


@dataclass(frozen=True)
class Protokolllage:
    eintraege: tuple[LogEintrag, ...] = ()
    jetzt: datetime.datetime | None = None
    #: Beginn dieser Sitzung - Fehler seitdem sind ein FEHLER, aeltere eine WARNUNG.
    sitzung_ab: datetime.datetime | None = None
    lesbar: bool = True


_LOGZEILE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\s*\] (.*)$")


def protokoll_lesen(pfad: str, schwanz_bytes: int = PROTOKOLL_SCHWANZ_BYTES) -> tuple[bool, tuple[LogEintrag, ...]]:
    """Liest das Ende der Protokolldatei in Eintraege.

    Returns:
        ``(lesbar, eintraege)``. Gibt es die Datei nicht, ist das kein Fehler (``(True, ())``).
    """
    try:
        if not os.path.isfile(pfad):
            return True, ()
        groesse = os.path.getsize(pfad)
        with open(pfad, "rb") as datei:
            if groesse > schwanz_bytes:
                datei.seek(groesse - schwanz_bytes)
                datei.readline()                      # angebrochene Zeile verwerfen
            zeilen = datei.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False, ()
    eintraege: list[dict] = []
    for zeile in zeilen:
        treffer = _LOGZEILE.match(zeile)
        if treffer:
            try:
                zeit = datetime.datetime.strptime(treffer.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                zeit = None
            eintraege.append({"zeit": zeit, "stufe": treffer.group(2).upper(), "text": treffer.group(3),
                              "rueck": False})
        elif eintraege:
            letzter = eintraege[-1]
            if zeile.startswith("Traceback (most recent call last)"):
                letzter["rueck"] = True
            # Folgezeilen gehoeren zum Eintrag; die letzte Zeile einer Rueckverfolgung ist die Ausnahme.
            if zeile.strip() and not zeile.startswith((" ", "\t")):
                letzter["letzte"] = zeile.strip()
    return True, tuple(
        LogEintrag(e["zeit"], e["stufe"], (e["text"] + (" | " + e["letzte"] if e.get("letzte") else "")),
                   e["rueck"]) for e in eintraege)


def _gruppenschluessel(text: str) -> str:
    """Gleiche Fehler mit anderen Zahlen/Pfaden zaehlen als einer."""
    return re.sub(r"\d+", "#", text)[:100]


def _gruppen(eintraege: Iterable[LogEintrag]) -> list[tuple[int, LogEintrag]]:
    gruppen: dict[str, list[LogEintrag]] = {}
    for e in eintraege:
        gruppen.setdefault(_gruppenschluessel(e.text), []).append(e)
    rang = sorted(gruppen.values(), key=lambda g: (-len(g), g[-1].zeit or datetime.datetime.min))
    return [(len(g), g[-1]) for g in rang]


def pruefe_protokoll(lage: Protokolllage) -> list[Befund]:
    """Fehler und Warnungen der letzten 24 Stunden aus der Protokolldatei.

    Ein ``ERROR`` seit Beginn dieser Sitzung ist ein FEHLER (das Programm laeuft gerade mit einem Problem), ein
    aelterer eine WARNUNG. Warnungen der Protokollstufe ``WARNING`` sind HINWEISE.
    """
    if not lage.lesbar:
        return [Befund(WARNUNG, "protokoll_unlesbar", "Die Protokolldatei ps5converter.log ist nicht lesbar")]
    jetzt = lage.jetzt or datetime.datetime.now()
    grenze = jetzt - datetime.timedelta(hours=PROTOKOLL_FRIST_H)
    frisch = [e for e in lage.eintraege if e.zeit is not None and e.zeit >= grenze]
    befunde: list[Befund] = []

    fehler = [e for e in frisch if e.stufe in ("ERROR", "CRITICAL")]
    for anzahl, e in _gruppen(fehler)[:PROTOKOLL_GRUPPEN_MAX]:
        in_sitzung = lage.sitzung_ab is not None and e.zeit is not None and e.zeit >= lage.sitzung_ab
        befunde.append(Befund(
            FEHLER if in_sitzung else WARNUNG, "protokoll_fehler",
            "%dx %s im Protokoll%s, zuletzt %s: %s" % (
                anzahl, e.stufe, " (mit Rückverfolgung)" if e.rueckverfolgung else "",
                e.zeit.strftime("%d.%m. %H:%M") if e.zeit else "?", e.text[:200])))
    rest = len({_gruppenschluessel(e.text) for e in fehler}) - PROTOKOLL_GRUPPEN_MAX
    if rest > 0:
        befunde.append(Befund(WARNUNG, "protokoll_fehler", "... und %d weitere Fehlerarten im Protokoll" % rest))

    warnungen = [e for e in frisch if e.stufe == "WARNING"]
    for anzahl, e in _gruppen(warnungen)[:PROTOKOLL_GRUPPEN_MAX]:
        befunde.append(Befund(
            HINWEIS, "protokoll_warnung",
            "%dx WARNING, zuletzt %s: %s" % (
                anzahl, e.zeit.strftime("%d.%m. %H:%M") if e.zeit else "?", e.text[:200])))
    return befunde


# ---------------------------------------------------------------------------
# Liegen gebliebene Arbeitsordner und Teildateien
# ---------------------------------------------------------------------------
ART_ARBEIT = "arbeitsordner"
ART_TEIL = "teildatei"
ART_PROBE = "schreibprobe"


@dataclass(frozen=True)
class Rest:
    pfad: str
    art: str
    bytes: int = 0
    alter_s: float = 0.0
    unvollstaendig: bool = False        # Messung wegen des Zeitbudgets abgebrochen: "mindestens"


@dataclass(frozen=True)
class Restelage:
    reste: tuple[Rest, ...] = ()
    #: Laeuft eine Aufgabe, gehoeren die Ordner zu ihr.
    arbeit_laeuft: bool = False


_PAKET_ENDUNGEN = (".ffpfsc", ".ffpfs", ".exfat", ".ffpkg", ".pkg")


#: Namen mit dem Vorsatz ``ps5conv_``, die kein Rest sind: der Testordner, den der Bericht selbst empfiehlt
#: (``$env:TEMP\ps5conv_pruefung\konfig``), und der Zwischenspeicher fuer Metadaten.
KEINE_RESTE = frozenset({"ps5conv_pruefung", "ps5converter_meta_cache"})


def rest_art(name: str) -> str:
    """Welche Art Rest ein Name ist - oder ``""``, wenn er keiner ist."""
    klein = name.lower()
    if klein in KEINE_RESTE:
        return ""
    if klein.startswith((".ps5conv_tmp_write_test_", ".ps5conv_doktor_probe")):
        return ART_PROBE
    if klein.startswith("ps5conv_") or klein == "ps4dib_arbeit":
        return ART_ARBEIT
    if klein.endswith(".partial"):
        return ART_TEIL
    if klein.endswith((".tmp", ".teil", ".neu", ".part")) and any(e in klein for e in _PAKET_ENDUNGEN):
        # ".teil" und ".neu": der Teilbau neben dem Ziel und der Bau neben der Quelle (Reste-Karte, 13.11.2026).
        return ART_TEIL
    return ""


def _groesse(pfad: str, frist: float) -> tuple[int, bool]:
    """Groesse eines Pfades; bricht bei ``frist`` (time.monotonic) ab -> ``(bisher, True)``."""
    try:
        if os.path.isfile(pfad):
            return os.path.getsize(pfad), False
    except OSError:
        return 0, False
    summe = 0
    for wurzel, _ordner, dateien in os.walk(pfad):
        for name in dateien:
            if time.monotonic() > frist:
                return summe, True
            try:
                summe += os.path.getsize(os.path.join(wurzel, name))
            except OSError:
                continue
    return summe, False


def reste_suchen(ordner: Iterable[str], *, jetzt: float | None = None,
                 zeitbudget: float = RESTE_ZEITBUDGET_S) -> tuple[Rest, ...]:
    """Sucht in den ``ordner`` (nur oberste Ebene) nach Resten dieses Programms.

    Gemessen am 29.10.2026: Eine ``.ps5conv_tmp_write_test_*``-Datei blieb nach einem hart beendeten Lauf liegen;
    nach Abbruechen bleiben auch ``ps5conv_*``-Arbeitsordner und halbe ``*.partial`` stehen und belegen
    zweistellige Gigabyte, ohne dass es jemand merkt.
    """
    jetzt = time.time() if jetzt is None else jetzt
    frist = time.monotonic() + zeitbudget
    gesehen: set[str] = set()
    gefunden: list[Rest] = []
    for wurzel in ordner:
        if not wurzel:
            continue
        schluessel = os.path.normcase(os.path.abspath(wurzel))
        if schluessel in gesehen or not os.path.isdir(wurzel):
            continue
        gesehen.add(schluessel)
        try:
            namen = os.listdir(wurzel)
        except OSError:
            continue
        for name in namen:
            art = rest_art(name)
            if not art:
                continue
            pfad = os.path.join(wurzel, name)
            try:
                alter = max(0.0, jetzt - os.path.getmtime(pfad))
            except OSError:
                continue
            groesse, abgebrochen = _groesse(pfad, frist) if art != ART_PROBE else (0, False)
            gefunden.append(Rest(pfad, art, groesse, alter, abgebrochen))
    return tuple(gefunden)


def _lesbar(n: int) -> str:
    wert = float(n)
    for einheit in ("B", "KB", "MB", "GB", "TB"):
        if wert < 1024 or einheit == "TB":
            return ("%d %s" % (wert, einheit)) if einheit == "B" else ("%.1f %s" % (wert, einheit))
        wert /= 1024
    return "%d B" % n


def pruefe_reste(lage: Restelage) -> list[Befund]:
    """Liegen gebliebene Arbeitsordner, Teildateien und Schreibproben (nur ohne laufende Aufgabe)."""
    if lage.arbeit_laeuft:
        return []
    alt = [r for r in lage.reste if r.alter_s >= RESTE_MINDESTALTER_S]
    echte = sorted((r for r in alt if r.art != ART_PROBE), key=lambda r: -r.bytes)
    proben = [r for r in alt if r.art == ART_PROBE]
    befunde: list[Befund] = []
    if echte:
        gesamt = sum(r.bytes for r in echte)
        mindestens = any(r.unvollstaendig for r in echte)
        nennung = "; ".join("%s (%s%s)" % (r.pfad, "mind. " if r.unvollstaendig else "", _lesbar(r.bytes))
                            for r in echte[:RESTE_MAX_NENNUNGEN])
        mehr = len(echte) - RESTE_MAX_NENNUNGEN
        befunde.append(Befund(
            WARNUNG, "reste_liegen_geblieben",
            "%d Arbeitsordner/Teildateien von früheren Läufen belegen %s%s: %s%s" % (
                len(echte), "mind. " if mindestens else "", _lesbar(gesamt), nennung,
                " ... und %d weitere" % mehr if mehr > 0 else "")))
    if proben:
        befunde.append(Befund(
            HINWEIS, "schreibprobe_liegt",
            "%d Schreibprobe(n) eines hart beendeten Laufs liegen herum (leere Dateien): %s" % (
                len(proben), "; ".join(r.pfad for r in proben[:RESTE_MAX_NENNUNGEN]))))
    return befunde


# ---------------------------------------------------------------------------
# Eingehaengte Laufwerke
# ---------------------------------------------------------------------------
ART_OSFMOUNT = "osfmount"
ART_DOKAN = "dokan"


@dataclass(frozen=True)
class Laufwerkslage:
    """Laufwerksbuchstaben, die ein Einhaengewerkzeug dieses Programms angelegt haben koennte."""
    laufwerke: tuple[tuple[str, str], ...] = ()          # (Buchstabe, Art)
    #: Laeuft eine Aufgabe, gehoeren die Laufwerke zu ihr.
    arbeit_laeuft: bool = False


def laufwerke_messen(arbeit_laeuft: bool = False) -> Laufwerkslage:
    """Liest die Buchstaben D: bis Z:, hinter denen ein OSFMount-Abbild oder ein UFS2-Dokan-Laufwerk steckt.

    Gemessen am 04.11.2026: Nach Abbruechen blieben drei OSFMount-Abbilder (X:, Y:, Z:, ohne Dateisystem und nicht
    erreichbar) und ein Dokan-Laufwerk (W:, "UFS2") im Explorer stehen. Niemand bemerkte es, bis der Nutzer sie sah -
    ``GetLogicalDrives`` zeigt sie, aber kein Bericht nannte sie.
    """
    if sys.platform != "win32" or arbeit_laeuft:
        return Laufwerkslage((), arbeit_laeuft)
    import ctypes
    kern = ctypes.windll.kernel32
    ziel_puffer = ctypes.create_unicode_buffer(1024)
    name_puffer = ctypes.create_unicode_buffer(64)
    gefunden: list[tuple[str, str]] = []
    for index in range(3, 26):
        buchstabe = chr(65 + index)
        if not kern.QueryDosDeviceW(buchstabe + ":", ziel_puffer, 1024):
            continue
        if ziel_puffer.value.startswith("\\Device\\OSFMDisk"):
            gefunden.append((buchstabe, ART_OSFMOUNT))
        elif (kern.GetVolumeInformationW(buchstabe + ":\\", None, 0, None, None, None, name_puffer, 64)
              and name_puffer.value.upper() == "UFS2"):
            gefunden.append((buchstabe, ART_DOKAN))
    return Laufwerkslage(tuple(gefunden), arbeit_laeuft)


def pruefe_laufwerke(lage: Laufwerkslage) -> list[Befund]:
    """Ein Hinweis auf eingehaengte OSFMount-/UFS2-Laufwerke (nur ohne laufende Aufgabe).

    Ein Hinweis und keine Warnung: Ob jemand das Abbild bewusst eingehaengt hat, laesst sich von hier nicht sehen.
    """
    if lage.arbeit_laeuft or not lage.laufwerke:
        return []
    teile = []
    for buchstabe, art in lage.laufwerke:
        teile.append("%s: (%s)" % (buchstabe, "OSFMount-Abbild" if art == ART_OSFMOUNT else "UFS2 über Dokan"))
    osf = [b for b, a in lage.laufwerke if a == ART_OSFMOUNT]
    dokan = [b for b, a in lage.laufwerke if a == ART_DOKAN]
    wie = []
    if osf:
        wie.append("OSFMount: OSFMount.com -d -m %s:" % osf[0] + (" (usw.)" if len(osf) > 1 else ""))
    if dokan:
        wie.append("Dokan: dokanctl /u %s" % dokan[0] + (" (usw.)" if len(dokan) > 1 else ""))
    return [Befund(
        HINWEIS, "laufwerke_eingehaengt",
        "%d eingehängte(s) Laufwerk(e), die dieses Programm angelegt haben könnte, sind noch da: %s. Waren sie nicht "
        "gewollt, so aushängen - %s" % (len(lage.laufwerke), ", ".join(teile), "; ".join(wie)))]


# ---------------------------------------------------------------------------
# Ressourcen und Prozesse
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ressourcenlage:
    gdi: int = 0
    user: int = 0
    handles: int = 0
    faeden: int = 0
    #: Namen von Werkzeug-Prozessen, die dieses Programm gestartet hat und die gerade laufen.
    werkzeuge: tuple[str, ...] = ()
    arbeit_laeuft: bool = False
    #: Prozesse, die das Programm selbst mitzaehlt (``ps5_pkg_werkzeug.laufende``), falls psutil fehlt.
    getrackte_werkzeuge: int = 0


def _stufe(wert: int, warnung: int, fehler: int) -> str | None:
    if wert >= fehler:
        return FEHLER
    if wert >= warnung:
        return WARNUNG
    return None


def pruefe_ressourcen(lage: Ressourcenlage) -> list[Befund]:
    """GDI-/USER-Objekte, Handles, Faeden und verwaiste Werkzeug-Prozesse."""
    befunde: list[Befund] = []
    for name, wert, warn, fehl, grenze in (
            ("GDI-Objekte", lage.gdi, GDI_WARNUNG, GDI_FEHLER, 10000),
            ("USER-Objekte", lage.user, USER_WARNUNG, USER_FEHLER, 10000),
            ("Handles", lage.handles, HANDLES_WARNUNG, HANDLES_FEHLER, 0),
            ("Faden", lage.faeden, FADEN_WARNUNG, FADEN_FEHLER, 0)):
        stufe = _stufe(wert, warn, fehl)
        if stufe:
            befunde.append(Befund(
                stufe, "ressource_knapp",
                "%d %s%s - ein Fenster oder Zeitgeber gibt etwas nicht frei" % (
                    wert, name, " (Windows-Grenze %d)" % grenze if grenze else "")))
    verwaist = len(lage.werkzeuge) or lage.getrackte_werkzeuge
    if verwaist and not lage.arbeit_laeuft:
        namen = ", ".join(sorted(set(lage.werkzeuge))) if lage.werkzeuge else "Werkzeug"
        befunde.append(Befund(
            WARNUNG, "prozess_verwaist",
            "%d Werkzeug-Prozess(e) laufen (%s), obwohl kein Auftrag mehr offen ist - sie halten Dateien im "
            "Zielordner offen" % (verwaist, namen)))
    return befunde


def ressourcen_messen(arbeit_laeuft: bool = False, getrackt: int = 0) -> Ressourcenlage:
    """Liest Windows-Ressourcen, Handles, Faeden und Kind-Prozesse dieses Prozesses."""
    gdi = user = 0
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            from ctypes import wintypes  # noqa: PLC0415
            # Ohne Typen faellt das Handle (ein Zeiger, -1 fuer den eigenen Prozess) auf 32 Bit zusammen, und die
            # Funktion antwortet 0 - gemessen am 03.11.2026, als die Pruefung stumm nichts sah.
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            user32.GetGuiResources.restype = wintypes.DWORD
            prozess = kernel32.GetCurrentProcess()
            gdi = int(user32.GetGuiResources(prozess, 0))
            user = int(user32.GetGuiResources(prozess, 1))
        except Exception:  # noqa: BLE001
            gdi = user = 0
    handles = faeden = 0
    werkzeuge: list[str] = []
    try:
        import psutil  # noqa: PLC0415
        eigener = psutil.Process()
        faeden = int(eigener.num_threads())
        if sys.platform == "win32":
            handles = int(eigener.num_handles())
        else:
            handles = int(eigener.num_fds())
        for kind in eigener.children(recursive=True):
            try:
                name = (kind.name() or "").lower()
            except psutil.Error:
                continue
            if name.endswith(".exe"):
                name = name[:-4]
            if any(name == w or name.startswith(w) for w in WERKZEUG_PROZESSE):
                werkzeuge.append(name)
    except Exception:  # noqa: BLE001
        import threading  # noqa: PLC0415
        faeden = threading.active_count()
    return Ressourcenlage(gdi=gdi, user=user, handles=handles, faeden=faeden, werkzeuge=tuple(werkzeuge),
                          arbeit_laeuft=arbeit_laeuft, getrackte_werkzeuge=getrackt)


# ---------------------------------------------------------------------------
# Wiederaufnahmepunkte
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Wiederaufnahmepunkt:
    zustand: str
    aktualisiert: datetime.datetime | None
    aufgabe: str = ""
    quelle: str = ""


@dataclass(frozen=True)
class Wiederaufnahmelage:
    punkte: tuple[Wiederaufnahmepunkt, ...] = ()
    jetzt: datetime.datetime | None = None
    arbeit_laeuft: bool = False
    lesbar: bool = True


def wiederaufnahme_lesen(pfad: str) -> tuple[bool, tuple[Wiederaufnahmepunkt, ...]]:
    """Liest ``runtime_checkpoint.json``. Fehlt die Datei, ist das in Ordnung."""
    try:
        if not os.path.isfile(pfad):
            return True, ()
        with open(pfad, "r", encoding="utf-8-sig") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return False, ()
    jobs = daten.get("jobs") if isinstance(daten, dict) else None
    if not isinstance(jobs, dict):
        return True, ()
    punkte = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        try:
            zeit = datetime.datetime.fromisoformat(str(job.get("updated", "")))
        except ValueError:
            zeit = None
        punkte.append(Wiederaufnahmepunkt(str(job.get("state", "")), zeit, str(job.get("mode", "")),
                                          str(job.get("src", ""))))
    return True, tuple(punkte)


def pruefe_wiederaufnahme(lage: Wiederaufnahmelage) -> list[Befund]:
    """Unfertige Laeufe, die das Programm beim Beenden oder nach einem Absturz zurueckliess."""
    if not lage.lesbar:
        return [Befund(WARNUNG, "wiederaufnahme_unlesbar", "runtime_checkpoint.json ist nicht lesbar")]
    if lage.arbeit_laeuft:
        return []
    jetzt = lage.jetzt or datetime.datetime.now()
    offen = [p for p in lage.punkte if p.zustand == "in_progress"]
    if not offen:
        return []
    alt = [p for p in offen if p.aktualisiert is not None
           and (jetzt - p.aktualisiert).days >= WIEDERAUFNAHME_ALT_TAGE]
    befunde = []
    if alt:
        befunde.append(Befund(
            WARNUNG, "wiederaufnahme_veraltet",
            "%d unfertige Wiederaufnahmepunkte sind älter als %d Tage und werden nie fortgesetzt: %s" % (
                len(alt), WIEDERAUFNAHME_ALT_TAGE, "; ".join(
                    "%s %s" % (p.aufgabe, p.quelle) for p in alt[:3]))))
    frische = len(offen) - len(alt)
    if frische:
        befunde.append(Befund(
            HINWEIS, "wiederaufnahme_offen",
            "%d unfertige Wiederaufnahmepunkte: das Programm wurde während eines Laufs beendet" % frische))
    return befunde


# ---------------------------------------------------------------------------
# Einstellungen und Ablage
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Einstellungslage:
    #: Gemerkte Pfade, die es nicht mehr gibt: ``(Schluessel, Pfad)``.
    fehlende_pfade: tuple[tuple[str, str], ...] = ()
    geprueft: int = 0
    ordner_beschreibbar: bool = True
    ordner_frei_mb: float = -1.0
    lesbar: bool = True


_PFADSCHLUESSEL = re.compile(r"(_ziel|_dir|_ordner|_path|_quelle|_folders|_basis)$|^(src|dst|temp_dir)$")
_ABSOLUT = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")
#: Wechseldatentraeger kommen und gehen - ein fehlender Pfad ist nur ein Hinweis.
EINSTELLUNG_PFADE_MAX = 40


def einstellungen_messen(config_datei: str) -> Einstellungslage:
    """Liest paths.json, prueft die gemerkten Pfade und den Ordner der Einstellungen."""
    ordner = os.path.dirname(os.path.abspath(config_datei))
    beschreibbar = True
    try:
        os.makedirs(ordner, exist_ok=True)
        probe = os.path.join(ordner, ".ps5conv_diag_probe")
        with open(probe, "wb") as datei:
            datei.write(b"ok")
        os.remove(probe)
    except OSError:
        beschreibbar = False
    try:
        frei = shutil.disk_usage(ordner).free / (1024 * 1024)
    except OSError:
        frei = -1.0
    try:
        if not os.path.isfile(config_datei):
            return Einstellungslage(ordner_beschreibbar=beschreibbar, ordner_frei_mb=frei)
        with open(config_datei, "r", encoding="utf-8-sig") as datei:
            daten = json.load(datei)
        if not isinstance(daten, dict):
            return Einstellungslage(ordner_beschreibbar=beschreibbar, ordner_frei_mb=frei, lesbar=False)
    except (OSError, ValueError):
        return Einstellungslage(ordner_beschreibbar=beschreibbar, ordner_frei_mb=frei, lesbar=False)
    fehlend: list[tuple[str, str]] = []
    geprueft = 0
    for schluessel, wert in daten.items():
        if not _PFADSCHLUESSEL.search(str(schluessel)):
            continue
        werte = wert if isinstance(wert, list) else [wert]
        for pfad in werte:
            if not isinstance(pfad, str) or not _ABSOLUT.match(pfad) or pfad.startswith("\\\\"):
                continue
            if geprueft >= EINSTELLUNG_PFADE_MAX:
                break
            geprueft += 1
            try:
                if not os.path.exists(pfad):
                    fehlend.append((str(schluessel), pfad))
            except OSError:
                fehlend.append((str(schluessel), pfad))
    return Einstellungslage(tuple(fehlend), geprueft, beschreibbar, frei)


def pruefe_einstellungen(lage: Einstellungslage) -> list[Befund]:
    befunde: list[Befund] = []
    if not lage.lesbar:
        befunde.append(Befund(FEHLER, "einstellungen_unlesbar",
                              "Die Einstellungsdatei paths.json ist nicht lesbar - alle Einstellungen gelten als leer"))
    if not lage.ordner_beschreibbar:
        befunde.append(Befund(FEHLER, "einstellungen_nicht_schreibbar",
                              "Der Ordner der Einstellungen ist nicht beschreibbar - nichts wird gemerkt"))
    if 0 <= lage.ordner_frei_mb < 100:
        befunde.append(Befund(FEHLER, "einstellungen_voll",
                              "Auf dem Laufwerk der Einstellungen sind nur %.0f MB frei" % lage.ordner_frei_mb))
    if lage.fehlende_pfade:
        nennung = "; ".join("%s=%s" % p for p in lage.fehlende_pfade[:4])
        mehr = len(lage.fehlende_pfade) - 4
        befunde.append(Befund(
            HINWEIS, "gemerkter_pfad_fehlt",
            "%d von %d gemerkten Pfaden gibt es nicht mehr (Laufwerk abgesteckt?): %s%s" % (
                len(lage.fehlende_pfade), lage.geprueft, nennung, " ... und %d weitere" % mehr if mehr > 0 else "")))
    return befunde


# ---------------------------------------------------------------------------
# Uebersetzungen
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Sprachlage:
    schluessel: int = 0
    fehlend: tuple[tuple[str, str], ...] = ()
    leer: tuple[tuple[str, str], ...] = ()
    platzhalter: tuple[tuple[str, str], ...] = ()


_PLATZHALTER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}")
SPRACHEN = ("de", "en", "es", "it", "fr")


def sprachen_messen(texte: dict, sprachen: tuple[str, ...] = SPRACHEN) -> Sprachlage:
    """Fehlt einem Text eine Sprache, ist sie leer, oder stimmen die ``{Platzhalter}`` nicht mit Deutsch ueberein?"""
    fehlend, leer, platz = [], [], []
    for schluessel, eintrag in texte.items():
        if not isinstance(eintrag, dict):
            fehlend.append((str(schluessel), "*"))
            continue
        deutsch = set(_PLATZHALTER.findall(str(eintrag.get("de", ""))))
        for sprache in sprachen:
            if sprache not in eintrag:
                fehlend.append((str(schluessel), sprache))
            elif not str(eintrag[sprache]).strip():
                leer.append((str(schluessel), sprache))
            elif sprache != "de" and set(_PLATZHALTER.findall(str(eintrag[sprache]))) != deutsch:
                platz.append((str(schluessel), sprache))
    return Sprachlage(len(texte), tuple(fehlend), tuple(leer), tuple(platz))


def pruefe_sprachen(lage: Sprachlage) -> list[Befund]:
    """Eine fehlende Uebersetzung zeigt die Oberflaeche als Schluessel; ein falscher Platzhalter wirft beim Anzeigen."""
    befunde: list[Befund] = []
    for kennung, was, liste, stufe in (
            ("text_fehlt", "fehlende Sprachfassung", lage.fehlend, FEHLER),
            ("text_leer", "leere Sprachfassung", lage.leer, WARNUNG),
            ("text_platzhalter", "Platzhalter weicht von Deutsch ab", lage.platzhalter, FEHLER)):
        if liste:
            befunde.append(Befund(
                stufe, kennung, "%d x %s, z. B. %s" % (
                    len(liste), was, ", ".join("%s (%s)" % p for p in liste[:3]))))
    return befunde


# ---------------------------------------------------------------------------
# Abstuerze und Fangnetze
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Absturzlage:
    unbehandelte_fehler: int = 0
    absturzdatei_bytes: int = 0
    absturzdatei: str = ""
    abzug_aktiv: bool = True


def pruefe_abstuerze(lage: Absturzlage) -> list[Befund]:
    befunde: list[Befund] = []
    if lage.unbehandelte_fehler > 0:
        befunde.append(Befund(
            FEHLER, "unbehandelte_fehler",
            "%d unbehandelte Fehler in dieser Sitzung (Abschnitt „Unbehandelte Fehler“ im Bericht)"
            % lage.unbehandelte_fehler))
    if lage.absturzdatei_bytes > 0:
        befunde.append(Befund(
            WARNUNG, "harter_absturz",
            "%s ist nicht leer (%s): dort steht ein früherer harter Absturz" % (
                lage.absturzdatei or "Absturzabzug", _lesbar(lage.absturzdatei_bytes))))
    if not lage.abzug_aktiv:
        befunde.append(Befund(WARNUNG, "absturzabzug_aus",
                              "Der Absturzabzug (faulthandler) ist aus - ein harter Absturz bliebe spurlos"))
    return befunde


# ---------------------------------------------------------------------------
# Mitgelieferte Werkzeug-Programme und .NET
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Werkzeuglage:
    #: Werkzeuge, die fehlen: ``(Name, Grund)``.
    fehlend: tuple[tuple[str, str], ...] = ()
    #: ``None`` = nicht geprueft.
    dotnet_da: bool | None = None
    geprueft: int = 0


#: Programme, die es nur als Windows-Bau gibt (Namen beginnen so). Unter Linux und macOS fehlen sie von Haus aus - das
#: ist kein Befund, wie schon bei der Probe der mitgelieferten Programme im Hauptmodul. Bis 05.11.2026 meldete die
#: Betriebspruefung dort eine WARNUNG; die Mac-CI (``--anzeige-diagnose`` muss 0 liefern) wurde davon rot.
NUR_WINDOWS = ("OrbisPkgTool",)


def werkzeuge_messen(suchen: "dict[str, Callable[[], str]]",
                     dotnet: "Callable[[], str] | None" = None,
                     plattform: str | None = None) -> Werkzeuglage:
    """Gibt es die Programme, die der Anwender zum Packen und Lesen braucht - und laufen sie auf .NET?

    Der Doktor prueft Python-Module und Ordner, nicht die Programmdateien selbst: Fehlt ``ffpfsc-pkg-tool.exe`` (vom
    Virenscanner entfernt, beim Entpacken verloren), zeigt PS5 PKG erst beim Start eine Meldung.

    Args:
        suchen: Name -> Funktion, die den Pfad liefert (leer = nicht gefunden).
        dotnet: Liefert den Ordner der .NET-Laufzeit (leer = keine).
        plattform: ``sys.platform``; ausserhalb von ``win32`` entfallen die Programme aus ``NUR_WINDOWS``.
    """
    if (plattform or sys.platform) != "win32":
        suchen = {n: f for n, f in suchen.items() if not n.startswith(NUR_WINDOWS)}
    fehlend: list[tuple[str, str]] = []
    for name, suche in suchen.items():
        try:
            pfad = suche()
        except Exception as exc:  # noqa: BLE001 - eine kaputte Suche ist selbst ein Befund
            fehlend.append((name, "Suche scheiterte: %s" % exc))
            continue
        if not pfad:
            fehlend.append((name, "nicht gefunden"))
        elif not os.path.isfile(pfad):
            fehlend.append((name, "Datei fehlt: %s" % pfad))
        else:
            try:
                if os.path.getsize(pfad) == 0:
                    fehlend.append((name, "Datei ist leer: %s" % pfad))
            except OSError as exc:
                fehlend.append((name, "nicht lesbar: %s" % exc))
    dotnet_da: bool | None = None
    if dotnet is not None:
        try:
            dotnet_da = bool(dotnet())
        except Exception:  # noqa: BLE001
            dotnet_da = False
    return Werkzeuglage(tuple(fehlend), dotnet_da, len(suchen))


def pruefe_werkzeuge(lage: Werkzeuglage) -> list[Befund]:
    befunde = [Befund(WARNUNG, "werkzeug_fehlt", "%s fehlt (%s) - die zugehörige Funktion läuft nicht" % p)
               for p in lage.fehlend]
    if lage.dotnet_da is False:
        befunde.append(Befund(
            WARNUNG, "dotnet_fehlt",
            ".NET-Laufzeit nicht gefunden - PS5 PKG (ffpfsc-pkg-tool) und UFS2Tool starten nicht"))
    return befunde


# ---------------------------------------------------------------------------
# Python-Pakete gegen requirements.txt
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Abhaengigkeitslage:
    #: ``(Paket, Soll, Ist)``; ``Ist`` leer = nicht installiert.
    abweichungen: tuple[tuple[str, str, str], ...] = ()
    geprueft: int = 0


_PIN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-+!]+)\s*(?:;\s*(.*))?$")


def _version_installiert(name: str) -> str:
    from importlib import metadata  # noqa: PLC0415
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return ""


def abhaengigkeiten_messen(requirements: str, installiert: "Callable[[str], str] | None" = None,
                           plattform: str | None = None) -> Abhaengigkeitslage:
    """Vergleicht die festgenagelten Pakete (``name==version``) mit den installierten.

    Zeilen mit Bedingung ``sys_platform == "win32"`` gelten nur dort. Unfestgenagelte Zeilen (z. B. ``zlib-ng``) und
    Kommentare werden uebersprungen. Gibt es die Datei nicht (gebautes Programm), entfaellt die Pruefung.
    """
    holen = installiert or _version_installiert
    plattform = plattform or sys.platform
    try:
        with open(requirements, "r", encoding="utf-8-sig") as datei:
            zeilen = datei.read().splitlines()
    except OSError:
        return Abhaengigkeitslage()
    abweichungen: list[tuple[str, str, str]] = []
    geprueft = 0
    for zeile in zeilen:
        treffer = _PIN.match(zeile.split("#", 1)[0])
        if not treffer:
            continue
        name, soll, bedingung = treffer.group(1), treffer.group(2), (treffer.group(3) or "").strip()
        if bedingung:
            m = re.search(r"sys_platform\s*==\s*['\"]([^'\"]+)['\"]", bedingung)
            if m and m.group(1) != plattform:
                continue
        geprueft += 1
        ist = holen(name)
        if ist != soll:
            abweichungen.append((name, soll, ist))
    return Abhaengigkeitslage(tuple(abweichungen), geprueft)


def pruefe_abhaengigkeiten(lage: Abhaengigkeitslage) -> list[Befund]:
    """Ein fehlendes Paket ist eine WARNUNG (die Funktion dahinter faellt aus), eine andere Fassung ein HINWEIS."""
    befunde = []
    for name, soll, ist in lage.abweichungen:
        if not ist:
            befunde.append(Befund(WARNUNG, "paket_fehlt", "%s %s (requirements.txt) ist nicht installiert" % (name, soll)))
        else:
            befunde.append(Befund(HINWEIS, "paket_abweichend",
                                  "%s ist in Fassung %s installiert, requirements.txt nagelt %s fest" % (name, ist, soll)))
    return befunde


# ---------------------------------------------------------------------------
# Was andere Abschnitte schon melden
# ---------------------------------------------------------------------------
#: Eine Testabdeckung, die so alt ist, sagt nichts mehr ueber den heutigen Quelltext.
ABDECKUNG_ALT_TAGE = 30
_ABDECKUNG = re.compile(r"Testabdeckung:\s*([\d.,]+)\s*%.*gemessen vor ([\d.,]+) Tagen")


def pruefe_optimierung(zeilen: Iterable[str]) -> list[Befund]:
    """Das Alter der gemessenen Testabdeckung (Abschnitt "Optimierung")."""
    for zeile in zeilen:
        treffer = _ABDECKUNG.search(str(zeile))
        if treffer:
            try:
                tage = float(treffer.group(2).replace(",", "."))
            except ValueError:
                return []
            if tage > ABDECKUNG_ALT_TAGE:
                return [Befund(HINWEIS, "abdeckung_veraltet",
                               "Die Testabdeckung (%s %%) wurde vor %.0f Tagen gemessen - neu messen: "
                               "coverage run -m pytest -q" % (treffer.group(1), tage))]
    return []
def pruefe_doktor(zeilen: Iterable[str]) -> list[Befund]:
    """Zeilen des Doktors: ``[FEHL]`` ist ein FEHLER, ``[ !! ]`` ein HINWEIS (so stuft der Doktor selbst)."""
    befunde: list[Befund] = []
    for zeile in zeilen:
        text = str(zeile).strip()
        if text.startswith(DOKTOR_FEHLER):
            befunde.append(Befund(FEHLER, "doktor_fehler", text[len(DOKTOR_FEHLER):].strip()))
        elif text.startswith(DOKTOR_HINWEIS):
            befunde.append(Befund(HINWEIS, "doktor_hinweis", text[len(DOKTOR_HINWEIS):].strip()))
    return befunde


def pruefe_werkzeugpflege(zeilen: Iterable[str]) -> list[Befund]:
    """Abweichungen zwischen mitgelieferten Dateien und der Lizenzdatei."""
    befunde: list[Befund] = []
    for zeile in zeilen:
        text = str(zeile).strip()
        if text.startswith(("ohne Zeile in der Lizenzdatei", "Zeile ohne Datei im Ordner")):
            befunde.append(Befund(WARNUNG, "werkzeugpflege", text))
    return befunde


def pruefe_fremdwerkzeuge(zeilen: Iterable[str]) -> list[Befund]:
    """Treiber, die fehlen (``NICHT INSTALLIERT``)."""
    return [Befund(HINWEIS, "fremdwerkzeug_fehlt", str(z).strip()[:300])
            for z in zeilen if "NICHT INSTALLIERT" in str(z)]


def pruefe_eigenschaften(zeilen: Iterable[str]) -> list[Befund]:
    """Die eingebauten Zusicherungen (``Eigenschaften: n geprüft, m VERLETZT``)."""
    return [Befund(FEHLER, "eigenschaft_verletzt", str(z).strip()) for z in zeilen if "VERLETZT" in str(z)]


# ---------------------------------------------------------------------------
# Alles zusammen
# ---------------------------------------------------------------------------
_RANG = {FEHLER: 0, WARNUNG: 1, HINWEIS: 2}


@dataclass
class Betriebsergebnis(Pruefergebnis):
    """Die Befunde der Betriebspruefung und die Namen dessen, was dabei tatsaechlich geprueft wurde.

    Ohne die Liste waere "keine Auffaelligkeit" nicht zu unterscheiden von "nichts gemessen".
    """

    geprueft: list[str] = field(default_factory=list)


def pruefe_alles(*, protokoll: Protokolllage | None = None, reste: Restelage | None = None,
                 ressourcen: Ressourcenlage | None = None, wiederaufnahme: Wiederaufnahmelage | None = None,
                 einstellungen: Einstellungslage | None = None, sprachen: Sprachlage | None = None,
                 abstuerze: Absturzlage | None = None, doktor: Iterable[str] | None = None,
                 werkzeugpflege: Iterable[str] | None = None, fremdwerkzeuge: Iterable[str] | None = None,
                 eigenschaften: Iterable[str] | None = None, werkzeuge: Werkzeuglage | None = None,
                 abhaengigkeiten: Abhaengigkeitslage | None = None,
                 optimierung: Iterable[str] | None = None,
                 laufwerke: Laufwerkslage | None = None) -> Betriebsergebnis:
    """Fuehrt alle Betriebspruefungen aus. Fehlt eine Messung, entfaellt nur ihr Teil."""
    befunde: list[Befund] = []
    geprueft: list[str] = []
    for name, lage, pruefer in (
            ("Werkzeug-Programme und .NET", werkzeuge, pruefe_werkzeuge),
            ("Python-Pakete (requirements.txt)", abhaengigkeiten if abhaengigkeiten and abhaengigkeiten.geprueft
             else None, pruefe_abhaengigkeiten),
            ("Alter der Testabdeckung", optimierung, pruefe_optimierung),
            ("Protokoll (24 h)", protokoll, pruefe_protokoll),
            ("liegen gebliebene Reste", reste, pruefe_reste),
            ("eingehängte Laufwerke", laufwerke, pruefe_laufwerke),
            ("Prozesse und Ressourcen", ressourcen, pruefe_ressourcen),
            ("Wiederaufnahmepunkte", wiederaufnahme, pruefe_wiederaufnahme),
            ("Einstellungen und Pfade", einstellungen, pruefe_einstellungen),
            ("Übersetzungen", sprachen, pruefe_sprachen),
            ("Abstürze und Fangnetze", abstuerze, pruefe_abstuerze),
            ("Doktor", doktor, pruefe_doktor),
            ("Werkzeugpflege", werkzeugpflege, pruefe_werkzeugpflege),
            ("Treiber und Fremdwerkzeuge", fremdwerkzeuge, pruefe_fremdwerkzeuge),
            ("Zusicherungen", eigenschaften, pruefe_eigenschaften)):
        if lage is not None:
            geprueft.append(name)
            befunde.extend(pruefer(lage))
    befunde.sort(key=lambda b: (_RANG.get(b.schwere, 9), b.kennung, b.text))
    return Betriebsergebnis(befunde, geprueft)


#: Kopfzeilen als Vorgabe; die Oberflaeche reicht uebersetzte Fassungen herein (wie ``anzeige_diagnose.MELDUNGEN``).
MELDUNGEN: dict[str, str] = {
    "gesamt_sauber": "Gesamt: keine Auffälligkeit (Darstellung und Betrieb geprüft)",
    "gesamt_zaehlung": "Gesamt: {teile} (Darstellung {darstellung}, Betrieb {betrieb})",
    "betrieb_sauber": "Betrieb: keine Auffälligkeit",
    "betrieb_zaehlung": "Betrieb: {teile}",
    "betrieb_anzahl": "{anzahl} x {schwere}",
    "schwere_fehler": "FEHLER",
    "schwere_warnung": "WARNUNG",
    "schwere_hinweis": "HINWEIS",
}


def _satz(texte: "dict[str, str] | None", kennung: str, **werte) -> str:
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return MELDUNGEN[kennung].format(**werte)


def _zaehlung(befunde: list[Befund], texte: "dict[str, str] | None") -> str:
    teile = []
    for schwere in (FEHLER, WARNUNG, HINWEIS):
        anzahl = sum(1 for b in befunde if b.schwere == schwere)
        if anzahl:
            teile.append(_satz(texte, "betrieb_anzahl", anzahl=anzahl,
                               schwere=_satz(texte, "schwere_%s" % schwere.lower())))
    return ", ".join(teile)


def zusammenfassung(ergebnis: Pruefergebnis, texte: "dict[str, str] | None" = None) -> str:
    """Eine Zeile fuer die Betriebspruefung."""
    if not ergebnis.befunde:
        return _satz(texte, "betrieb_sauber")
    return _satz(texte, "betrieb_zaehlung", teile=_zaehlung(ergebnis.befunde, texte))


def gesamturteil(darstellung: Pruefergebnis, betrieb: Pruefergebnis,
                 texte: "dict[str, str] | None" = None) -> str:
    """Eine Zeile ueber alles: Darstellung und Betrieb zusammen."""
    alle = list(darstellung.befunde) + list(betrieb.befunde)
    if not alle:
        return _satz(texte, "gesamt_sauber")

    def klein(erg: Pruefergebnis) -> str:
        return str(len(erg.befunde))
    return _satz(texte, "gesamt_zaehlung", teile=_zaehlung(alle, texte),
                 darstellung=klein(darstellung), betrieb=klein(betrieb))


def sauber(darstellung: Pruefergebnis, betrieb: Pruefergebnis) -> bool:
    """Wahr, wenn weder Darstellung noch Betrieb einen FEHLER oder eine WARNUNG haben (Hinweise zaehlen nicht)."""
    return darstellung.sauber and betrieb.sauber


#: Wie viele Befunde einer Art einzeln im Bericht stehen.
BEFUND_GRENZE = 12


def bericht_zeilen(ergebnis: Betriebsergebnis, texte: "dict[str, str] | None" = None) -> list[str]:
    """Die Zeilen des Berichtsabschnitts "Betriebspruefung": Urteil, Liste dessen, was geprueft wurde, Befunde."""
    zeilen = [zusammenfassung(ergebnis, texte),
              "geprüft: %s" % (", ".join(ergebnis.geprueft) if ergebnis.geprueft else "nichts (keine Messung möglich)")]
    if not ergebnis.befunde:
        return zeilen
    zeilen.append("")
    gesehen: dict[str, int] = {}
    for befund in ergebnis.befunde:
        gesehen[befund.kennung] = gesehen.get(befund.kennung, 0) + 1
        if gesehen[befund.kennung] <= BEFUND_GRENZE:
            zeilen.append(str(befund))
    for kennung, anzahl in gesehen.items():
        if anzahl > BEFUND_GRENZE:
            zeilen.append("... und %d weitere der Art %s" % (anzahl - BEFUND_GRENZE, kennung))
    return zeilen
