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
import tempfile
from collections.abc import Callable, MutableMapping
from typing import Any

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
            logger.debug("fc-match nicht ausführbar: %s", exc)
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
            logger.debug("Admin-Prüfung fehlgeschlagen: %s", exc)
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
        logger.debug("STARTUPINFO nicht verfügbar: %s", exc)
    return flags


# ---------------------------------------------------------------------------
# Dateien und Ordner im System oeffnen
# ---------------------------------------------------------------------------
#: Gruende, die :func:`oeffnen_versuchen` nennt. Fest deutsch waeren sie ein
#: Sprachleck: Dieses Modul darf ``i18n`` nicht importieren - es soll ohne
#: die Oberflaeche benutzbar bleiben -, und die Saetze gehen in Dialoge.
#: Wer uebersetzte will, reicht sie als ``texte`` herein; dasselbe Muster
#: wie in ``pkg_merger.MELDUNGEN`` und ``shadowmount_generation.MELDUNGEN``.
OEFFNEN_MELDUNGEN: dict[str, str] = {
    "kein_pfad": "Es wurde kein Pfad angegeben.",
    "nicht_da": "Die Datei oder der Ordner ist nicht (mehr) da.",
    "kein_programm": "Es gibt kein Programm, das dafür zuständig ist.",
    "starter_fehler": "{starter} meldete Fehler {code}{hinweis}",
}

#: Warum das Herunterfahren nicht ging. Der Grund steht in einem
#: Hinweisfenster, deshalb dasselbe Muster wie oben. Bis zum 06.09.2026 gab
#: :func:`herunterfahren` diese Sätze fest auf Deutsch zurück.
HERUNTERFAHR_MELDUNGEN: dict[str, str] = {
    "kein_befehl": "kein Befehl verfügbar",
    "nicht_gefunden": "{befehl} nicht gefunden",
    "fehlgeschlagen": "{befehl}: {grund}",
    "exit_code": "{befehl}: Exit {code}: {ausgabe}",
}


def _herunterfahr_satz(texte: "dict[str, str] | None", kennung: str,
                       **werte) -> str:
    """Eine Vorlage aus :data:`HERUNTERFAHR_MELDUNGEN`, übersetzt wenn möglich."""
    vorlage = (texte or {}).get(kennung) or HERUNTERFAHR_MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return HERUNTERFAHR_MELDUNGEN[kennung].format(**werte)


#: So lange wartet :func:`oeffnen_versuchen` auf ``open``/``xdg-open``. Beide
#: kehren normalerweise sofort zurueck; laeuft der Starter laenger, hat er das
#: Programm im Vordergrund gestartet.
_STARTER_WARTEZEIT_S = 3.0


def oeffnen_versuchen(pfad: str,
                      texte: "dict[str, str] | None" = None) -> tuple[bool, str]:
    """Oeffnet eine Datei oder einen Ordner - und nennt den Grund bei Misserfolg.

    **Warum es diese Fassung gibt.** :func:`datei_oeffnen` liefert einen
    blossen ``bool``, und der bedeutet nicht "geoeffnet", sondern nur
    "Versuch abgesetzt": Unter Windows kommt nach ``os.startfile`` immer
    ``True``; wirft es (weil die Datei fehlt), faengt der Browser-Ausweg
    den Fall ab und meldet ebenfalls Erfolg. Unter POSIX wurde der
    Rueckgabewert von ``xdg-open`` nie gelesen und seine Fehlerausgabe nach
    ``DEVNULL`` geschickt. ``False`` entstand damit fast nur bei leerem
    Pfad.

    Am 06.09.2026 gemessen: Fuer einen Pfad, den es gar nicht gibt, melden
    beide Funktionen ``True``. Die sechs ``if not ...`` im Hauptprogramm
    traten deshalb nie zu - vier davon haetten eine Fehlermeldung gezeigt,
    zwei schrieben nur ins Protokoll. Der Anwender drueckte einen Knopf,
    bei dem nichts geschah.

    Args:
        pfad: Datei, Ordner oder Adresse mit Schema.
        texte: Vorlagen je Kennung aus :data:`OEFFNEN_MELDUNGEN`; fehlt
            eine, gilt die eingebaute.

    Returns:
        ``(Erfolg, Grund)``. Bei Erfolg ist der Grund leer. Der Grund ist
        fuer den Anwender gedacht und nennt, was schiefging - nicht den
        Pfad, den kennt der Aufrufer selbst.
    """
    vorlagen = dict(OEFFNEN_MELDUNGEN)
    if texte:
        vorlagen.update({k: v for k, v in texte.items() if v})

    def _satz(kennung: str, **werte) -> str:
        try:
            return vorlagen[kennung].format(**werte)
        except (KeyError, IndexError, ValueError):
            # Eine unbrauchbare Vorlage darf den Grund nicht verschlucken.
            try:
                return OEFFNEN_MELDUNGEN[kennung].format(**werte)
            except Exception:      # noqa: BLE001
                return kennung

    ziel = str(pfad or "")
    if not ziel:
        return (False, _satz("kein_pfad"))
    # Eine Adresse mit Schema geht an den Browser und muss hier nicht
    # liegen. Alles andere ist ein Pfad - und der haeufigste Grund, warum
    # nichts geschieht, ist schlicht, dass es ihn nicht gibt.
    if "://" not in ziel and not os.path.exists(ziel):
        return (False, _satz("nicht_da"))
    try:
        if IST_WINDOWS:
            os.startfile(ziel)  # type: ignore[attr-defined]
            return (True, "")
        starter = "open" if IST_MACOS else "xdg-open"
        if shutil.which(starter):
            # Nicht mehr nach DEVNULL: Die Fehlerausgabe des Starters ist
            # das Einzige, was ueberhaupt sagt, woran es lag.
            #
            # Aber in eine Datei, nicht in eine Pipe, und nur kurz gewartet.
            # Bis v1.9.24 lief hier subprocess.run mit capture_output und 20 s
            # Zeitgrenze - im Hauptfaden. Ohne erkannte Arbeitsumgebung startet
            # xdg-open das Programm im Vordergrund; es erbte die Pipes, run
            # wartete die vollen 20 s (Fenster eingefroren), lief in den
            # Timeout, und der Browser-Ausweg unten oeffnete die Datei ein
            # zweites Mal. Laeuft der Starter nach der Wartezeit noch, hat er
            # das Programm gestartet - das ist Erfolg.
            with tempfile.TemporaryFile() as fehlerausgabe:
                lauf = subprocess.Popen(
                    [starter, ziel], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=fehlerausgabe,
                    start_new_session=True)
                try:
                    code = lauf.wait(timeout=_STARTER_WARTEZEIT_S)
                except subprocess.TimeoutExpired:
                    return (True, "")
                if code == 0:
                    return (True, "")
                fehlerausgabe.seek(0)
                zeilen = fehlerausgabe.read().decode(
                    "utf-8", "replace").strip().splitlines()
            return (False, _satz("starter_fehler", starter=starter,
                                 code=code,
                                 hinweis=(": " + zeilen[0][:160]) if zeilen else ""))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Öffnen über das System fehlgeschlagen (%s): %s", ziel, exc)
        grund = str(exc)[:160]
    else:
        grund = _satz("kein_programm")
    # Letzter Ausweg: Der Browser oeffnet HTML/PDF und faellt sonst auf den
    # Dateimanager der Arbeitsumgebung zurueck.
    try:
        import webbrowser

        if webbrowser.open(ziel):
            return (True, "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Browser-Fallback fehlgeschlagen (%s): %s", ziel, exc)
    return (False, grund)


def datei_oeffnen(pfad: str) -> bool:
    """Oeffnet eine Datei oder einen Ordner im Standardprogramm des Systems.

    Huelle um :func:`oeffnen_versuchen` fuer Aufrufer, denen der Grund
    gleichgueltig ist. Wer eine Meldung zeigen will, nimmt die andere.

    Returns:
        True, wenn geoeffnet werden konnte.
    """
    return oeffnen_versuchen(pfad)[0]


def im_dateimanager_zeigen(pfad: str) -> bool:
    """Oeffnet den Dateimanager und markiert darin die angegebene Datei.

    Unter Linux gibt es dafuer keinen einheitlichen Befehl. Der Weg ueber die
    D-Bus-Schnittstelle ``org.freedesktop.FileManager1`` beherrschen Nautilus,
    Dolphin, Nemo und Thunar; scheitert er, wird ersatzweise der uebergeordnete
    Ordner geoeffnet - ohne Markierung, aber am richtigen Ort.

    **Was hier fehlte.** Bis zum 06.09.2026 hiess der Rueckgabewert nur
    "Anzeigeversuch abgesetzt": Der Explorer-Aufruf ging ohne jede Pruefung
    hinaus und meldete Erfolg, auch fuer einen Pfad, den es gar nicht gibt.
    Beide Aufrufer im Hauptprogramm ("Im Ordner zeigen" in der Bibliothek
    und beim Diagnosebericht) haben ein ``if not ...``, das deshalb nie
    zutrat - und sie schreiben im Misserfolgsfall ohnehin nur ins
    Protokoll. Ein Knopf, bei dem nichts geschah.

    Returns:
        True, wenn der Pfad da ist und angezeigt werden konnte.
    """
    ziel = os.path.abspath(str(pfad or ""))
    if not ziel or not os.path.exists(ziel):
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

    **Umlenkbar.** Steht ``PS5CONV_KONFIGORDNER`` in der Umgebung, gilt
    dieser Ordner. Das ist fuer Pruefstaende gedacht: Sie druecken echte
    Knoepfe, und echte Knoepfe speichern echt. Ohne die Umlenkung
    schreibt jeder Lauf in den Bestand des Anwenders - betroffen waeren
    unter anderem ``metadata_online`` (damit verlaesst die Title-ID den
    Rechner) und ``shutdown_after_success`` (damit faehrt der Rechner
    nach der naechsten Konvertierung herunter).

    Returns:
        Absoluter Ordnerpfad. Der Ordner wird nicht angelegt.
    """
    umgelenkt = os.environ.get("PS5CONV_KONFIGORDNER", "").strip()
    if umgelenkt:
        return umgelenkt

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
# Zertifikate fuer HTTPS in der gebauten Fassung
# ---------------------------------------------------------------------------
#: Wo verbreitete Systeme ihr CA-Buendel ablegen, in der Reihenfolge, die
#: auch Go durchsucht (crypto/x509/root_linux.go). ``/etc/ssl/cert.pem``
#: deckt zusaetzlich macOS ab, wo Apple die Datei pflegt.
CA_BUENDEL_KANDIDATEN = (
    "/etc/ssl/certs/ca-certificates.crt",                 # Debian, Ubuntu, Gentoo, Arch
    "/etc/pki/tls/certs/ca-bundle.crt",                   # Fedora, RHEL 6
    "/etc/ssl/ca-bundle.pem",                             # openSUSE
    "/etc/pki/tls/cacert.pem",                            # OpenELEC
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",  # CentOS, RHEL 7
    "/etc/ssl/cert.pem",                                  # Alpine, macOS
)


def zertifikate_bereitstellen(umgebung: MutableMapping[str, str] | None = None,
                              gefroren: bool | None = None,
                              ist_windows: bool = IST_WINDOWS,
                              standard: Any = None,
                              gibt_es: Callable[[str], bool] = os.path.isfile) -> str:
    """Zeigt die mitgebaute OpenSSL auf das CA-Buendel des Systems.

    Die gebaute Fassung bringt ihre eigene OpenSSL mit, und die sucht
    Zertifikate dort, wo sie gebaut wurde. Gemessen am 17.09.2026: im
    Linux-Bau v1.9.24 unter ``/usr/lib/ssl`` (nur Debian und Ubuntu haben
    das), in den Mac-Buendeln v1.8.100 unter
    ``/Library/Frameworks/Python.framework/Versions/3.12/etc/openssl`` bzw.
    ``/usr/local/etc/openssl@3``. Fehlt der Ort, scheitert jeder HTTPS-Abruf
    mit ``CERTIFICATE_VERIFY_FAILED`` - AMPR-Fassungen,
    Aktualisierungspruefung, Titel-Nachschlag.

    Nichts geschieht unter Windows (Python liest dort den
    Zertifikatsspeicher des Systems), aus dem Quelltext heraus (die OpenSSL
    passt dann zum System), wenn ``SSL_CERT_FILE`` oder ``SSL_CERT_DIR``
    schon gesetzt ist, und wenn der eingebaute Ort vorhanden ist.

    Die Parameter sind fuer Pruefstaende; das Programm ruft ohne.

    Returns:
        Der gesetzte Pfad, sonst leer.
    """
    umgebung = os.environ if umgebung is None else umgebung
    if gefroren is None:
        gefroren = bool(getattr(sys, "frozen", False))
    if ist_windows or not gefroren:
        return ""
    if umgebung.get("SSL_CERT_FILE") or umgebung.get("SSL_CERT_DIR"):
        return ""
    if standard is None:
        import ssl

        standard = ssl.get_default_verify_paths()
    # cafile und capath sind None, wenn es Datei bzw. Ordner nicht gibt.
    if standard.cafile or standard.capath:
        return ""
    for kandidat in CA_BUENDEL_KANDIDATEN:
        if gibt_es(kandidat):
            umgebung["SSL_CERT_FILE"] = kandidat
            logger.info("Zertifikate fuer HTTPS: %s", kandidat)
            return kandidat
    logger.warning("Kein CA-Buendel gefunden - HTTPS-Abrufe werden scheitern.")
    return ""


# ---------------------------------------------------------------------------
# Herunterfahren
# ---------------------------------------------------------------------------
def herunterfahren(texte: "dict[str, str] | None" = None) -> tuple[bool, str]:
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

    letzter_fehler = _herunterfahr_satz(texte, "kein_befehl")
    for befehl in befehle:
        if not shutil.which(befehl[0]):
            letzter_fehler = _herunterfahr_satz(texte, "nicht_gefunden",
                                               befehl=befehl[0])
            continue
        try:
            ergebnis = subprocess.run(
                befehl, capture_output=True, text=True, timeout=30, **prozess_flags(),  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001
            letzter_fehler = _herunterfahr_satz(texte, "fehlgeschlagen",
                                               befehl=befehl[0], grund=exc)
            continue
        if ergebnis.returncode == 0:
            return (True, " ".join(befehl))
        letzter_fehler = _herunterfahr_satz(
            texte, "exit_code", befehl=befehl[0], code=ergebnis.returncode,
            ausgabe=(ergebnis.stderr or ergebnis.stdout or "").strip())
    return (False, letzter_fehler)


# ---------------------------------------------------------------------------
# Windows-eigene Zusatzwerkzeuge
# ---------------------------------------------------------------------------
#: Werkzeuge, die es nur als Windows-Programm gibt und fuer die es unter Linux
#: und macOS keinen gleichwertigen Ersatz im Lieferumfang gibt. Der Wert nennt
#: den betroffenen Programmteil fuer die Meldung an den Benutzer.
#: Was wirklich nur unter Windows geht.
#:
#: ``UFS2Tool`` stand hier bis v1.8.72 mit "Lesen und Bauen von
#: .ffpkg-Abbildern" - das war unsere Packentscheidung, keine Grenze des
#: Werkzeugs: Es laeuft laut eigenem README unter Windows, macOS und
#: Linux, und alle Abbild-Operationen (newfs, makefs, extract, info,
#: fsck_ufs) arbeiten auf Dateien. Nur ``mount_udf`` braucht Dokan, und
#: das gibt es allein unter Windows. Seit v1.8.72 liegt fuer jede
#: Plattform ein eigenstaendiger Bau bei.
NUR_WINDOWS_WERKZEUGE = {
    "OSFMount": "Einhängen von Abbildern als Laufwerk (Ersatzweg)",
    "Dokan": "Einhängen von UFS2-Abbildern als Laufwerk (UFS2Tool mount_udf)",
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
        f"Unter {systemname()} steht dieser Weg nicht zur Verfügung."
    )


# ---------------------------------------------------------------------------
# Zwischenablage fuer Bilder
# ---------------------------------------------------------------------------
def bild_in_zwischenablage(png: bytes) -> bool:
    """Legt ein PNG-Bild in die Zwischenablage des Systems.

    Tk kann das nicht: ``clipboard_append`` kennt nur Text. Jedes System
    braucht deshalb einen eigenen Weg - Windows das Format ``CF_DIB`` ueber
    die Win32-Schnittstelle, macOS ``osascript`` und Linux ``wl-copy``
    (Wayland) oder ``xclip`` (X11), sofern eines davon installiert ist.

    Gebraucht in der Bibliothek ("Titelbild kopieren", seit 25.09.2026).

    Returns:
        True, wenn das Bild in der Zwischenablage liegt.
    """
    if not png:
        return False
    try:
        if IST_WINDOWS:
            return _bild_in_zwischenablage_windows(png)
        if IST_MACOS:
            return _bild_in_zwischenablage_macos(png)
        return _bild_in_zwischenablage_linux(png)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Bild nicht in die Zwischenablage gelegt: %s", exc)
        return False


def _bild_in_zwischenablage_windows(png: bytes) -> bool:
    """``CF_DIB``: eine BMP-Datei ohne ihren 14 Byte langen Dateikopf."""
    import ctypes
    import io
    from ctypes import wintypes

    from PIL import Image

    puffer = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(puffer, "BMP")
    dib = puffer.getvalue()[14:]

    cf_dib, gmem_moveable = 8, 0x0002
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    speicher = kernel32.GlobalAlloc(gmem_moveable, len(dib))
    if not speicher:
        return False
    zeiger = kernel32.GlobalLock(speicher)
    if not zeiger:
        kernel32.GlobalFree(speicher)
        return False
    ctypes.memmove(zeiger, dib, len(dib))
    kernel32.GlobalUnlock(speicher)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(speicher)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(cf_dib, speicher):
            kernel32.GlobalFree(speicher)
            return False
        # Ab hier gehoert der Speicher der Zwischenablage - nicht freigeben.
        return True
    finally:
        user32.CloseClipboard()


def _bild_in_zwischenablage_macos(png: bytes) -> bool:
    """Ueber eine Zwischendatei - ``osascript`` liest das Bild von dort."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as datei:
        datei.write(png)
        pfad = datei.name
    try:
        skript = ('set the clipboard to (read (POSIX file "%s") as «class PNGf»)'
                  % pfad.replace('"', '\\"'))
        ergebnis = subprocess.run(["osascript", "-e", skript],
                                  capture_output=True, timeout=15)
        return ergebnis.returncode == 0
    finally:
        try:
            os.remove(pfad)
        except OSError:
            pass


def _bild_in_zwischenablage_linux(png: bytes) -> bool:
    """``wl-copy`` oder ``xclip`` - beide bleiben im Hintergrund stehen.

    Sie halten die Auswahl, bis ein anderes Programm sie uebernimmt. Mit
    abgefangener Ausgabe wartete ``subprocess.run`` deshalb bis zur
    Zeitgrenze auf ein Dateiende, das nie kommt - daher ``DEVNULL``.
    """
    for befehl in (["wl-copy", "--type", "image/png"],
                   ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"]):
        if not shutil.which(befehl[0]):
            continue
        try:
            ergebnis = subprocess.run(befehl, input=png, timeout=15,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("%s gescheitert: %s", befehl[0], exc)
            continue
        if ergebnis.returncode == 0:
            return True
    return False
