# -*- coding: utf-8 -*-
"""PS5 Wee Tools - mitgeliefert und als eigenes Programm gestartet.

PS5 Wee Tools (andy-man, GPL-3.0) arbeitet mit dem NOR-Flash der Konsole,
nicht mit Spiel-Dumps: Konsolendaten aus einem NOR-Dump lesen, Partitionen
zerlegen und zusammensetzen, 2BLS-Dateien, UART-Terminal, EMC-Fehlerlog und
der SPIway-Flasher (Teensy 2.0), der den NOR auch **beschreibt**. Seit v1.9.29
liegt es bei; Herkunft und Stand in ``PS5-Wee-Tools-0.1.8/UPSTREAM.md``.

**Warum ein eigener Prozess.** Das Werkzeug ist ein Textmenue mit ``input()``
und ``os.system('cls')`` und braucht ein Konsolenfenster - das Programm hat
keins. Seine Pakete heissen ``tools``, ``utils``, ``lang`` und ``data``; im
selben Prozess waere eine Namenskollision nur eine Frage der Zeit. Und die
GPL-3.0 bleibt sauber getrennt: Das Werkzeug liegt bei, sein Code wird nicht
in das Programm uebernommen.

**Warum eine Kopie im Arbeitsordner.** wee-tools sucht ``config.ini`` *und*
seine Sprachdateien unter ``ROOT_PATH``. In einem PyInstaller-Bau ist das der
Ordner neben der Programmdatei - dort liegen bei uns keine Sprachdateien, jede
Uebersetzung fiele still weg. Als Quelltext ausgefuehrt ist ``ROOT_PATH``
dagegen sein eigener Ordner. Deshalb wird der mitgelieferte Ordner in den
Arbeitsordner gespiegelt und von dort ausgefuehrt: Die Sprachen gehen, die
Einstellungen ueberstehen den naechsten Start, und gelesene NOR-Dumps und
UART-Protokolle landen an einer festen, sichtbaren Stelle.
"""
from __future__ import annotations

import builtins
import os
import re
import shlex
import shutil
import sys
import traceback
from typing import Callable

#: Der mitgelieferte Ordner (siehe dort UPSTREAM.md und herkunft.json).
ORDNER = "PS5-Wee-Tools-0.1.8"
#: Der Einstieg des Werkzeugs.
EINSTIEG = "ps5-wee-tools.py"
#: Interner Modus der Programmdatei, der das Werkzeug ausfuehrt.
SELBSTAUFRUF = "--ps5-wee-tools"
#: Der Arbeitsordner neben dem Programm - wie "AMPR EMU updates".
ARBEITSORDNER_NAME = "PS5 Wee Tools"
#: Darin die Programmkopie, von der aus das Werkzeug laeuft.
KOPIE_NAME = "programm"
#: Das Projekt auf GitHub - Quelle fuer die Aktualisierungspruefung.
QUELLE = "andy-man/ps5-wee-tools"
#: Die Pakete des Werkzeugs. Allgemeine Namen: Sie duerfen nicht auf
#: gleichnamige Module treffen - im Projektordner liegt ein eigenes ``tools/``.
EIGENE_PAKETE = ("tools", "utils", "lang", "data")
#: Nicht in die Kopie: die Einstellungen des Anwenders und Bytecode.
NICHT_SPIEGELN = ("config.ini", "__pycache__")
#: Umgebungsvariablen, ueber die das Fenster dem Kindprozess etwas mitgibt.
UMGEBUNG_SPRACHE = "PS5CONV_WEE_SPRACHE"
UMGEBUNG_ARBEITSORDNER = "PS5CONV_WEE_ARBEITSORDNER"
#: Ohne diesen Schalter erbt ein Kindprozess derselben PyInstaller-Datei den
#: Auspackordner des Fensters - und der verschwindet, wenn das Fenster zugeht,
#: waehrend wee-tools noch offen ist. Gemessen: Der Bootloader von PyInstaller
#: 6.22.3 kennt ihn (runw.exe). Ausserhalb eines Baus wirkt er nicht.
UMGEBUNG_PYINSTALLER_NEU = "PYINSTALLER_RESET_ENVIRONMENT"
#: Unter Windows: ein eigenes Konsolenfenster fuer den Kindprozess.
CREATE_NEW_CONSOLE = 0x00000010

#: Terminalprogramme unter Linux, in der Reihenfolge, in der sie probiert
#: werden, samt dem Schalter, hinter dem der Befehl folgt.
LINUX_TERMINALS = (
    ("x-terminal-emulator", ("-e",)),
    ("gnome-terminal", ("--",)),
    ("konsole", ("-e",)),
    ("xfce4-terminal", ("-x",)),
    ("mate-terminal", ("-x",)),
    ("xterm", ("-e",)),
)

#: Die wenigen Saetze, die der Kindprozess selbst ausgibt - er kennt die
#: Oberflaeche nicht und bekommt nur ihre Sprache mit.
_TEXTE = {
    "de": {
        "abbruch": "PS5 Wee Tools wurde mit einem Fehler beendet (siehe oben).",
        "ordner": "Der Arbeitsordner ließ sich nicht anlegen: %s",
        "fehlt": "Der Ordner %s fehlt – PS5 Wee Tools ist nicht mitgeliefert.",
        "enter": "Enter schließt dieses Fenster.",
    },
    "en": {
        "abbruch": "PS5 Wee Tools ended with an error (see above).",
        "ordner": "The working folder could not be created: %s",
        "fehlt": "The folder %s is missing – PS5 Wee Tools is not included.",
        "enter": "Press Enter to close this window.",
    },
}


def text(schluessel: str, sprache: str = "") -> str:
    """Ein Satz fuer das Konsolenfenster - deutsch, sonst englisch."""
    return _TEXTE.get(sprache, _TEXTE["en"])[schluessel]


def fassung_lesen(wurzel: str) -> str:
    """``APP_VERSION`` aus ``lang/lang.py`` - gelesen, nicht importiert.

    Ein Import zoege das ganze Werkzeug samt ``pyserial`` nach sich; ein
    Diagnosebericht soll nichts starten. Ohne Ordner gibt es nichts zu lesen -
    ein leerer Pfad duerfte nicht relativ zum Arbeitsverzeichnis suchen.
    """
    if not wurzel:
        return ""
    try:
        with open(os.path.join(wurzel, "lang", "lang.py"), encoding="utf-8",
                  errors="replace") as datei:
            treffer = re.search(r"^APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
                                datei.read(), re.MULTILINE)
    except OSError:
        return ""
    return treffer.group(1) if treffer else ""


def startbefehl(*, eingefroren: bool, programm: str, hauptskript: str = "") -> list[str]:
    """Der Befehl, der das Werkzeug ueber den internen Modus startet.

    Args:
        eingefroren: Laeuft das Programm als PyInstaller-Bau?
        programm: ``sys.executable`` - die Programmdatei oder der Interpreter.
        hauptskript: Nur ohne Bau - die Hauptdatei des Programms.
    """
    if eingefroren:
        return [programm, SELBSTAUFRUF]
    return [programm, hauptskript, SELBSTAUFRUF]


def terminal_befehl(befehl: list[str], plattform: str,
                    finden: Callable[[str], "str | None"] = shutil.which
                    ) -> "list[str] | None":
    """Wickelt den Befehl in ein Terminalfenster.

    Returns:
        Unter Windows der Befehl selbst - das Fenster kommt dort ueber
        ``CREATE_NEW_CONSOLE``. Unter macOS ein Aufruf von Terminal.app,
        unter Linux der des ersten gefundenen Terminals; None, wenn es dort
        keins gibt.
    """
    if plattform.startswith("win"):
        return list(befehl)
    if plattform == "darwin":
        # Terminal.app nimmt den Befehl als AppleScript-Zeichenkette:
        # Rueckstrich und Anfuehrungszeichen muessen dafuer maskiert sein.
        skript = shlex.join(befehl).replace("\\", "\\\\").replace('"', '\\"')
        return ["osascript",
                "-e", 'tell application "Terminal" to do script "%s"' % skript,
                "-e", 'tell application "Terminal" to activate']
    for name, schalter in LINUX_TERMINALS:
        pfad = finden(name)
        if pfad:
            return [pfad, *schalter, *befehl]
    return None


def kindumgebung(basis: "dict[str, str]", *, sprache: str = "",
                 arbeitsordner: str = "") -> dict[str, str]:
    """Die Umgebung des Kindprozesses: eine Kopie mit drei Ergaenzungen."""
    umgebung = dict(basis)
    umgebung[UMGEBUNG_PYINSTALLER_NEU] = "1"
    if sprache:
        umgebung[UMGEBUNG_SPRACHE] = sprache
    if arbeitsordner:
        umgebung[UMGEBUNG_ARBEITSORDNER] = arbeitsordner
    return umgebung


def kopie_anlegen(wurzel: str, arbeitsordner: str, sprache: str = "") -> str:
    """Spiegelt den mitgelieferten Ordner nach ``<Arbeitsordner>/programm``.

    Die ``config.ini`` des Anwenders bleibt stehen. Fehlt sie, entsteht eine
    mit der Sprache des Programms, sofern das Werkzeug sie kennt - sonst
    waehlt es selbst nach der Systemsprache.

    Returns:
        Der Pfad der Kopie.
    """
    kopie = os.path.join(arbeitsordner, KOPIE_NAME)
    shutil.copytree(wurzel, kopie, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*NICHT_SPIEGELN))
    einstellungen = os.path.join(kopie, "config.ini")
    if not os.path.isfile(einstellungen):
        # Wie die config.ini des Werkzeugs selbst: mit Ton.
        zeilen = ["sound = 1"]
        if sprache and os.path.isfile(os.path.join(kopie, "i18n", sprache + ".json")):
            zeilen.append("lang = %s" % sprache)
        with open(einstellungen, "w", encoding="utf-8", newline="\n") as datei:
            datei.write("\n".join(zeilen) + "\n")
    return kopie


def module_abraeumen() -> list[str]:
    """Nimmt gleichnamige Module aus ``sys.modules`` - und nennt sie."""
    praefixe = tuple(paket + "." for paket in EIGENE_PAKETE)
    weg = [name for name in list(sys.modules)
           if name in EIGENE_PAKETE or name.startswith(praefixe)]
    for name in weg:
        del sys.modules[name]
    return weg


def pakete_festlegen(kopie: str) -> list[str]:
    """Legt die Pakete des Werkzeugs fest auf die Kopie.

    Sie haben kein ``__init__.py``, sind also Namensraum-Pakete. Nach PEP 420
    gewinnt beim Import ein gewoehnliches Paket gleichen Namens - egal, wo es
    im Suchpfad steht, auch ganz hinten. Ein ``utils`` in den site-packages
    haette wee-tools damit gebrochen, obwohl die Kopie vorn steht. Mit fest
    eingetragenem ``__path__`` entscheidet der Suchpfad nicht mehr mit.
    Gemessen am 19.09.2026: weder im Bau noch in der .venv gibt es solche
    Namen - heute. Die Absicherung gilt dem naechsten Paket.

    Returns:
        Die festgelegten Paketnamen.
    """
    import importlib.machinery  # noqa: PLC0415
    import types  # noqa: PLC0415

    festgelegt = []
    for name in EIGENE_PAKETE:
        ordner = os.path.join(kopie, name)
        if not os.path.isdir(ordner):
            continue
        spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
        spec.submodule_search_locations = [ordner]
        paket = types.ModuleType(name)
        paket.__spec__ = spec
        paket.__path__ = [ordner]
        paket.__package__ = name
        sys.modules[name] = paket
        festgelegt.append(name)
    return festgelegt


def konsole_bereitstellen() -> bool:
    """Sorgt fuer ein Konsolenfenster samt Ein- und Ausgabe.

    Die Programmdatei hat unter Windows keine Konsole (``console=False``);
    dort sind ``sys.stdin`` und ``sys.stdout`` ``None``. Dann wird eine
    Konsole angelegt und die drei Stroeme darauf gelegt. Vorhandene Stroeme -
    ein Terminal oder die Umleitung einer Pruefung - bleiben unangetastet.

    Returns:
        True, wenn Ein- und Ausgabe danach benutzbar sind.
    """
    if os.name == "nt" and (sys.stdout is None or sys.stdin is None):
        import ctypes  # noqa: PLC0415 - nur unter Windows gebraucht

        kernel32 = ctypes.windll.kernel32
        if not kernel32.GetConsoleWindow() and not kernel32.AllocConsole():
            return False
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace",
                          buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace",
                          buffering=1)
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    if os.name == "nt":
        _farben_einschalten()
    return sys.stdin is not None and sys.stdout is not None


def _farben_einschalten() -> None:
    """ANSI-Farben in der Windows-Konsole (ENABLE_VIRTUAL_TERMINAL_PROCESSING)."""
    try:
        import ctypes  # noqa: PLC0415

        kernel32 = ctypes.windll.kernel32
        ausgabe = kernel32.GetStdHandle(-11)
        modus = ctypes.c_uint32()
        if kernel32.GetConsoleMode(ausgabe, ctypes.byref(modus)):
            kernel32.SetConsoleMode(ausgabe, modus.value | 0x0004)
    except Exception:  # noqa: BLE001 - ohne Farben geht es auch
        return


def _beenden(code=None):
    """Ersatz fuer ``quit``/``exit``, die das ``site``-Modul sonst anlegt."""
    raise SystemExit(code)


def warten(sprache: str = "") -> None:
    """Haelt das Fenster offen, damit eine Meldung lesbar bleibt."""
    try:
        input("\n" + text("enter", sprache))
    except (EOFError, OSError, RuntimeError):
        return


def ausfuehren(wurzel: str, arbeitsordner: str,
               argumente: "list[str] | None" = None, sprache: str = "") -> int:
    """Fuehrt das Werkzeug in *diesem* Prozess aus - der interne Modus.

    Nur in einem eigenen Prozess aufrufen: Suchpfad, Arbeitsverzeichnis,
    ``sys.argv`` und ``sys.frozen`` werden dafuer umgestellt.

    Args:
        wurzel: Der mitgelieferte Ordner.
        arbeitsordner: Wohin Kopie, Einstellungen, Dumps und Protokolle gehen.
        argumente: Was dem Werkzeug durchgereicht wird (etwa eine Datei).
        sprache: Sprache des Programms, fuer die erste ``config.ini``.

    Returns:
        Der Rueckgabewert fuer ``sys.exit``.
    """
    if not konsole_bereitstellen():
        return 3
    try:
        os.makedirs(arbeitsordner, exist_ok=True)
        kopie = kopie_anlegen(wurzel, arbeitsordner, sprache)
    except OSError as exc:
        print(text("ordner", sprache) % exc)
        warten(sprache)
        return 1
    module_abraeumen()
    pakete_festlegen(kopie)
    # Fuer die Pakete braucht es den Suchpfad nicht mehr (siehe oben); er
    # bleibt fuer den Fall, dass eine neue Fassung ein Modul neben den
    # Einstieg legt.
    sys.path.insert(0, kopie)
    os.chdir(arbeitsordner)
    # wee-tools liest bei sys.frozen Einstellungen und Sprachdateien neben
    # sys.executable - dort liegen sie nicht. Ohne frozen nimmt es seinen
    # eigenen Ordner, also die Kopie (siehe UPSTREAM.md, Anpassung 1).
    if getattr(sys, "frozen", False):
        sys.frozen = False
    for name in ("quit", "exit"):
        if not hasattr(builtins, name):
            setattr(builtins, name, _beenden)
    einstieg = os.path.join(kopie, EINSTIEG)
    sys.argv = [einstieg, *(argumente or [])]
    try:
        # Nicht ueber runpy.run_path: Das schreibt beim Verlassen sys.argv[0]
        # zurueck. wee-tools nimmt mit args.pop(0) aber das erste Element aus
        # sys.argv selbst - ohne Argumente war die Liste danach leer, und das
        # Zurueckschreiben scheiterte mit IndexError. Genau das war der
        # Normalfall: Knopf, Hauptmenue, "Beenden" - am 19.09.2026 von
        # test_wee_tools gefunden.
        with open(einstieg, "rb") as datei:
            code = compile(datei.read(), einstieg, "exec")
        exec(code, {"__name__": "__main__", "__file__": einstieg,  # noqa: S102
                    "__builtins__": builtins})
    except SystemExit as ende:
        if ende.code is None or isinstance(ende.code, int):
            return ende.code or 0
        print(ende.code)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception:  # noqa: BLE001 - der Anwender soll sehen, was war
        traceback.print_exc()
        print("\n" + text("abbruch", sprache))
        warten(sprache)
        return 1
    return 0
