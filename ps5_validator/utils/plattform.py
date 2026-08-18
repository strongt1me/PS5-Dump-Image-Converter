"""Betriebssystem-Abstraktion fuer Windows, Linux und macOS.

Das Programm entstand als reine Windows-Anwendung. Schriftwahl, das Oeffnen von
Dateien im Standardprogramm, die Rechtepruefung und das Herunterfahren haengen
deshalb an Win32-Aufrufen, die es auf anderen Systemen nicht gibt. Dieses Modul
buendelt genau diese Stellen, damit der uebrige Quelltext ohne
Fallunterscheidung auskommt und eine weitere Plattform an einer Stelle
nachgezogen werden kann.

Bewusst ohne ``tkinter``-Import: Die Schriftfamilien werden schon beim Laden des
Moduls gebraucht - unter anderem in Vorgabewerten von Funktionssignaturen
(``font: tuple = (UI_SCHRIFT, 12, "bold")``), die Python bereits beim Import
auswertet. Zu diesem Zeitpunkt gibt es noch kein Tk-Fenster, ueber das sich die
vorhandenen Familien abfragen liessen. Die Linux-Variante fragt daher
``fc-match`` (fontconfig), das auf jedem Desktop mit X11 oder Wayland vorhanden
ist; die macOS-Variante sieht in den Schriftordnern des Systems nach, weil es
dort weder fontconfig noch eine ebenso schnelle Abfrage gibt.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger("PS5Converter.plattform")

# ---------------------------------------------------------------------------
# Plattform-Erkennung
# ---------------------------------------------------------------------------
IST_WINDOWS = sys.platform == "win32"
IST_MACOS = sys.platform == "darwin"
IST_LINUX = sys.platform.startswith("linux")
#: Alles ausser Windows - dort greifen POSIX-Wege (geteuid, xdg-open, ...).
IST_POSIX = not IST_WINDOWS


def systemname() -> str:
    """Kurzer, anzeigbarer Name des laufenden Betriebssystems."""
    if IST_WINDOWS:
        return "Windows"
    if IST_MACOS:
        return "macOS"
    if IST_LINUX:
        return "Linux"
    return sys.platform


# ---------------------------------------------------------------------------
# Schriftfamilien
# ---------------------------------------------------------------------------
# Reihenfolge = Vorliebe. Der erste tatsaechlich installierte Eintrag gewinnt.
# "Segoe UI" steht auch in der Linux-Liste ganz vorn: Wer die
# Microsoft-Kernschriften nachinstalliert hat, bekommt damit exakt das
# Windows-Schriftbild, fuer das die Abstaende im Fensteraufbau ausgelegt sind.
_LINUX_UI_KANDIDATEN = (
    "Segoe UI",
    "Ubuntu",
    "Cantarell",
    "Noto Sans",
    "DejaVu Sans",
    "Liberation Sans",
)
_LINUX_MONO_KANDIDATEN = (
    "Consolas",
    "Ubuntu Mono",
    "JetBrains Mono",
    "DejaVu Sans Mono",
    "Noto Sans Mono",
    "Liberation Mono",
)

# macOS bringt kein fontconfig mit. Geprueft wird deshalb ueber die
# Schriftdateien selbst: Zu jedem Familiennamen stehen die Dateinamen, unter
# denen ihn Apple bzw. der Microsoft-Office-Installer ablegt. Der
# Familienname - nicht der Dateiname - geht spaeter an Tk.
#
# "Segoe UI" steht wie in der Linux-Liste vorn: Wer Microsoft Office
# installiert hat, hat sie, und dann sitzt das Fenster exakt so, wie die
# Abstaende ausgelegt sind. Die beiden letzten Eintraege gehoeren zum
# Grundbestand jedes macOS und greifen immer.
_MACOS_UI_KANDIDATEN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Segoe UI", ("segoeui.ttf", "Segoe UI.ttf", "SegoeUI.ttf")),
    ("SF Pro Text", ("SF-Pro-Text-Regular.otf", "SFProText-Regular.otf")),
    ("Helvetica Neue", ("HelveticaNeue.ttc", "HelveticaNeue.dfont")),
    ("Lucida Grande", ("LucidaGrande.ttc", "LucidaGrande.dfont")),
)
_MACOS_MONO_KANDIDATEN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Consolas", ("consola.ttf", "Consolas.ttf")),
    ("SF Mono", ("SFMono-Regular.otf", "SF-Mono-Regular.otf")),
    ("Menlo", ("Menlo.ttc", "Menlo.ttf")),
    ("Monaco", ("Monaco.ttf", "Monaco.dfont")),
)
#: Ablageorte in der Reihenfolge, in der macOS selbst sucht. Der
#: Microsoft-Unterordner kommt von aelteren Office-Fassungen; neuere legen
#: ihre Schriften direkt unter /Library/Fonts ab.
_MACOS_SCHRIFTORDNER = (
    os.path.join(os.path.expanduser("~"), "Library", "Fonts"),
    "/Library/Fonts",
    "/Library/Fonts/Microsoft",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
)


def _fontconfig_familie(kandidaten: tuple[str, ...], ersatz: str) -> str:
    """Erste per fontconfig tatsaechlich vorhandene Familie aus ``kandidaten``.

    ``fc-match`` liefert immer eine Antwort - fehlt die gewuenschte Schrift,
    nennt es die Ersatzschrift des Systems. Deshalb wird der zurueckgegebene
    Familienname mit dem gefragten verglichen, statt nur den Rueckgabewert zu
    pruefen.

    Returns:
        Name einer installierten Familie, sonst ``ersatz``.
    """
    if not shutil.which("fc-match"):
        # Ohne fontconfig laesst sich nichts pruefen. Der Ersatzname ist eine
        # der Tk-Grundfamilien, die auf jedem X11-System aufgeloest wird.
        return ersatz
    for name in kandidaten:
        try:
            ergebnis = subprocess.run(
                ["fc-match", "-f", "%{family}", name],
                capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:  # noqa: BLE001 - Schriftwahl darf nie den Start verhindern
            logger.debug("fc-match nicht ausfuehrbar: %s", exc)
            return ersatz
        if ergebnis.returncode != 0:
            continue
        # fc-match kann mehrere durch Komma getrennte Namen liefern
        # (z. B. "DejaVu Sans,DejaVu Sans Book").
        gefunden = {teil.strip().lower() for teil in (ergebnis.stdout or "").split(",")}
        if name.lower() in gefunden:
            return name
    return ersatz


def _macos_familie(
    kandidaten: tuple[tuple[str, tuple[str, ...]], ...], ersatz: str
) -> str:
    """Erste Familie aus ``kandidaten``, deren Schriftdatei auf dem Rechner liegt.

    Bewusst ueber das Dateisystem statt ueber ein Werkzeug: ``fc-match`` gibt es
    unter macOS nur nach einer Homebrew-Installation, und
    ``system_profiler SPFontsDataType`` braucht mehrere Sekunden - zu lang fuer
    eine Abfrage, die beim Import laeuft.

    Returns:
        Name einer vorhandenen Familie, sonst ``ersatz``.
    """
    for name, dateinamen in kandidaten:
        for ordner in _MACOS_SCHRIFTORDNER:
            for datei in dateinamen:
                try:
                    if os.path.isfile(os.path.join(ordner, datei)):
                        return name
                except OSError as exc:  # noqa: PERF203 - Schriftwahl darf nie den Start verhindern
                    logger.debug("Schriftordner nicht lesbar (%s): %s", ordner, exc)
    return ersatz


def _schriften_ermitteln() -> tuple[str, str]:
    """Waehlt (Flaechenschrift, Festbreitenschrift) passend zum System."""
    if IST_WINDOWS:
        return ("Segoe UI", "Consolas")
    if IST_MACOS:
        # Die Ersatznamen sind Tk-Grundfamilien: Selbst wenn eine kuenftige
        # macOS-Fassung alle geprueften Dateien verschiebt, bleibt die
        # Oberflaeche lesbar.
        return (
            _macos_familie(_MACOS_UI_KANDIDATEN, "Helvetica"),
            _macos_familie(_MACOS_MONO_KANDIDATEN, "Courier"),
        )
    return (
        _fontconfig_familie(_LINUX_UI_KANDIDATEN, "Helvetica"),
        _fontconfig_familie(_LINUX_MONO_KANDIDATEN, "Courier"),
    )


UI_SCHRIFT, MONO_SCHRIFT = _schriften_ermitteln()


# ---------------------------------------------------------------------------
# Rechte
# ---------------------------------------------------------------------------
def ist_administrator() -> bool:
    """True, wenn der Prozess mit erhoehten Rechten laeuft.

    Windows fragt die UAC-Erhoehung ab, POSIX-Systeme die effektive
    Benutzerkennung. Unter Linux und macOS braucht das Programm diese Rechte
    nur, wenn es Abbilder als Geraet einhaengen soll - der uebrige Betrieb
    laeuft bewusst als normaler Benutzer.
    """
    if IST_WINDOWS:
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Admin-Pruefung fehlgeschlagen: %s", exc)
            return False
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        return False


# ---------------------------------------------------------------------------
# Prozessstart ohne sichtbares Fenster
# ---------------------------------------------------------------------------
def prozess_flags() -> dict[str, object]:
    """Zusatzargumente fuer ``subprocess``, die unter Windows Fenster unterdruecken.

    Auf anderen Systemen ist das Ergebnis leer: ``creationflags`` und
    ``startupinfo`` kennt nur die Windows-Implementierung, ein von null
    verschiedener Wert loest dort sonst einen ``ValueError`` aus.
    """
    if not IST_WINDOWS:
        return {}
    flags: dict[str, object] = {}
    keine_konsole = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if keine_konsole:
        flags["creationflags"] = keine_konsole
    try:
        info = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        info.wShowWindow = 0  # SW_HIDE
        flags["startupinfo"] = info
    except Exception as exc:  # noqa: BLE001
        logger.debug("STARTUPINFO nicht verfuegbar: %s", exc)
    return flags


# ---------------------------------------------------------------------------
# Dateien und Ordner im System oeffnen
# ---------------------------------------------------------------------------
def datei_oeffnen(pfad: str) -> bool:
    """Oeffnet eine Datei oder einen Ordner im Standardprogramm des Systems.

    Returns:
        True, wenn ein Oeffnungsversuch abgesetzt werden konnte.
    """
    ziel = str(pfad or "")
    if not ziel:
        return False
    try:
        if IST_WINDOWS:
            os.startfile(ziel)  # type: ignore[attr-defined]
            return True
        starter = "open" if IST_MACOS else "xdg-open"
        if shutil.which(starter):
            subprocess.Popen(
                [starter, ziel],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Oeffnen ueber das System fehlgeschlagen (%s): %s", ziel, exc)
    # Letzter Ausweg: Der Browser oeffnet HTML/PDF und faellt sonst auf den
    # Dateimanager der Arbeitsumgebung zurueck.
    try:
        import webbrowser

        return bool(webbrowser.open(ziel))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Browser-Fallback fehlgeschlagen (%s): %s", ziel, exc)
        return False


def im_dateimanager_zeigen(pfad: str) -> bool:
    """Oeffnet den Dateimanager und markiert darin die angegebene Datei.

    Unter Linux gibt es dafuer keinen einheitlichen Befehl. Der Weg ueber die
    D-Bus-Schnittstelle ``org.freedesktop.FileManager1`` beherrschen Nautilus,
    Dolphin, Nemo und Thunar; scheitert er, wird ersatzweise der uebergeordnete
    Ordner geoeffnet - ohne Markierung, aber am richtigen Ort.

    Returns:
        True, wenn ein Anzeigeversuch abgesetzt werden konnte.
    """
    ziel = os.path.abspath(str(pfad or ""))
    if not ziel:
        return False
    try:
        if IST_WINDOWS:
            # Das Komma gehoert zum Schalter, nicht zum Pfad - Explorer erwartet
            # exakt diese Schreibweise.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(ziel)])
            return True
        if IST_MACOS:
            subprocess.Popen(["open", "-R", ziel])
            return True
        if shutil.which("dbus-send"):
            ergebnis = subprocess.run(
                [
                    "dbus-send", "--session", "--print-reply",
                    "--dest=org.freedesktop.FileManager1",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:file://{ziel}", "string:",
                ],
                capture_output=True, timeout=10,
            )
            if ergebnis.returncode == 0:
                return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Anzeige im Dateimanager fehlgeschlagen (%s): %s", ziel, exc)
    ordner = ziel if os.path.isdir(ziel) else os.path.dirname(ziel)
    return datei_oeffnen(ordner)


# ---------------------------------------------------------------------------
# Konfigurationsablage
# ---------------------------------------------------------------------------
def konfigurationsordner(anwendung: str = "PS5ImageConverterPro") -> str:
    """Liefert den systemueblichen Ordner fuer die Einstellungen der Anwendung.

    Windows behaelt ``%APPDATA%``, damit vorhandene Installationen ihre
    gespeicherten Pfade und Designeinstellungen weiterhin finden. Linux folgt
    der XDG-Spezifikation, macOS der Application-Support-Konvention.

    Returns:
        Absoluter Ordnerpfad. Der Ordner wird nicht angelegt.
    """
    if IST_WINDOWS:
        basis = os.environ.get("APPDATA", "")
    elif IST_MACOS:
        basis = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        basis = os.environ.get("XDG_CONFIG_HOME", "") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    if not basis:
        import tempfile

        return tempfile.gettempdir()
    return os.path.join(basis, anwendung)


# ---------------------------------------------------------------------------
# Herunterfahren
# ---------------------------------------------------------------------------
def herunterfahren() -> tuple[bool, str]:
    """Faehrt den Rechner sofort herunter.

    Unter Linux gibt es dafuer je nach Init-System und Rechtelage mehrere Wege;
    sie werden der Reihe nach probiert. ``systemctl poweroff`` funktioniert auf
    Arbeitsplatzsystemen ueber polkit auch ohne Root-Rechte.

    Unter macOS geht der erste Weg ueber die Systemereignisse, weil er ohne
    Root-Rechte auskommt. Beim allerersten Mal fragt macOS dafuer die
    Erlaubnis zur Steuerung anderer Programme ab; wird sie verweigert, greift
    ``shutdown -h now`` - das setzt allerdings voraus, dass das Programm ohnehin
    mit erhoehten Rechten laeuft.

    Returns:
        (Erfolg, Meldung). Die Meldung nennt bei Misserfolg den letzten Fehler.
    """
    if IST_WINDOWS:
        # ``/f`` beendet auch fremde Programme ohne Rueckfrage - genau das ist
        # gewuenscht, damit der Rechner unbeaufsichtigt ausgeht.
        befehle: tuple[list[str], ...] = (["shutdown.exe", "/s", "/t", "0", "/f"],)
    elif IST_MACOS:
        befehle = (
            ["osascript", "-e", 'tell application "System Events" to shut down'],
            ["shutdown", "-h", "now"],
        )
    else:
        befehle = (
            ["systemctl", "poweroff"],
            ["shutdown", "-h", "now"],
            ["poweroff"],
        )

    letzter_fehler = "kein Befehl verfuegbar"
    for befehl in befehle:
        if not shutil.which(befehl[0]):
            letzter_fehler = f"{befehl[0]} nicht gefunden"
            continue
        try:
            ergebnis = subprocess.run(
                befehl, capture_output=True, text=True, timeout=30, **prozess_flags(),  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001
            letzter_fehler = f"{befehl[0]}: {exc}"
            continue
        if ergebnis.returncode == 0:
            return (True, " ".join(befehl))
        letzter_fehler = (
            f"{befehl[0]}: Exit {ergebnis.returncode}: "
            f"{(ergebnis.stderr or ergebnis.stdout or '').strip()}"
        )
    return (False, letzter_fehler)


# ---------------------------------------------------------------------------
# Windows-eigene Zusatzwerkzeuge
# ---------------------------------------------------------------------------
#: Werkzeuge, die es nur als Windows-Programm gibt und fuer die es unter Linux
#: und macOS keinen gleichwertigen Ersatz im Lieferumfang gibt. Der Wert nennt
#: den betroffenen Programmteil fuer die Meldung an den Benutzer.
NUR_WINDOWS_WERKZEUGE = {
    "OSFMount": "Einhaengen von Abbildern als Laufwerk (Ersatzweg)",
    "Dokan": "Einhaengen von UFS2-Abbildern (UFS2Tool)",
    "UFS2Tool": "Lesen und Bauen von .ffpkg-Abbildern",
}


def nur_windows_hinweis(werkzeug: str) -> str:
    """Einheitlicher Hinweistext, wenn ein Windows-Werkzeug fehlt.

    Der bisherige Quelltext meldete an diesen Stellen "Adminrechte fehlen" oder
    "nicht gefunden". Beides fuehrt ausserhalb von Windows in die Irre: Dort ist
    das Werkzeug nicht ungefunden, sondern es existiert schlicht nicht.
    """
    zweck = NUR_WINDOWS_WERKZEUGE.get(werkzeug, "")
    zusatz = f" ({zweck})" if zweck else ""
    return (
        f"{werkzeug} gibt es nur unter Windows{zusatz}. "
        f"Unter {systemname()} steht dieser Weg nicht zur Verfuegung."
    )
