#!/usr/bin/env bash
# =============================================================================
# PS5 Dump & Image Converter - Linux Build-Skript
# =============================================================================
# Gegenstueck zu Build_EXE.ps1. Erzeugt eine einzelne, eigenstaendige
# Programmdatei unter dist/.
#
# Aufruf:
#   chmod +x Build_Linux.sh
#   ./Build_Linux.sh
#
# Bewusst NICHT mit sudo starten: Das Programm braucht zum Bauen keine
# Root-Rechte, und ein als root gebautes dist/ gehoert danach root - der
# naechste Lauf als normaler Benutzer scheitert dann beim Aufraeumen.
# =============================================================================
set -uo pipefail

cd "$(dirname "$(readlink -f "$0")")" || exit 1
PROJEKT="$PWD"

rot=$'\033[0;31m'; gruen=$'\033[0;32m'; gelb=$'\033[1;33m'
blau=$'\033[0;36m'; grau=$'\033[0;90m'; aus=$'\033[0m'

meldung() { printf '%s%s%s\n' "$2" "$1" "$aus"; }

VERSION="$(sed -n 's/^APP_VERSION[[:space:]]*=[[:space:]]*["'"'"']\(.*\)["'"'"'].*/\1/p' \
    PS5ImageConverter_Pro_FINAL_revised.py | head -1)"
VERSION="${VERSION:-unbekannt}"
ARCH="$(uname -m)"
ZIELNAME="PS5_Dump_Image_Converter_${VERSION}_linux_${ARCH}"

echo
meldung "=============================================" "$blau"
meldung "  PS5 Dump & Image Converter - Linux Build   " "$blau"
meldung "  Version: $VERSION   Architektur: $ARCH     " "$blau"
meldung "=============================================" "$blau"
echo

if [ "$(id -u)" -eq 0 ]; then
    meldung "WARNUNG: Als root gestartet. dist/ gehoert danach root." "$gelb"
    meldung "         Besser als normaler Benutzer bauen." "$gelb"
    echo
fi

# --- Schritt 1: Interpreter waehlen ---------------------------------------
# Bevorzugt der Projekt-Interpreter aus .venv-linux: Damit entstehen Programm
# und Testlaeufe auf derselben Python-Version. Die Windows-Umgebung heisst
# .venv; ein eigener Name verhindert, dass beide sich auf einem gemeinsam
# genutzten Ordner (z. B. per WSL oder Netzlaufwerk) gegenseitig ueberschreiben.
meldung "[1/6] Pruefe Python-Installation..." "$gelb"
VENV="$PROJEKT/.venv-linux"
if [ -x "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
    if [ -z "$PYTHON" ]; then
        meldung "FEHLER: Python nicht gefunden. Bitte python3 installieren." "$rot"
        exit 1
    fi
    meldung "      Hinweis: .venv-linux fehlt - wird angelegt." "$gelb"
    if ! "$PYTHON" -m venv "$VENV" 2>/dev/null; then
        meldung "FEHLER: Virtuelle Umgebung nicht anlegbar." "$rot"
        meldung "        Fehlt das Paket python3-venv?" "$rot"
        exit 1
    fi
    PYTHON="$VENV/bin/python"
fi
meldung "      Interpreter: $PYTHON" "$grau"
meldung "      $("$PYTHON" --version 2>&1) gefunden." "$gruen"

# --- Schritt 2: Systempakete pruefen --------------------------------------
# Tcl/Tk und fontconfig kommen nicht ueber pip. Ohne Tk startet die
# Oberflaeche gar nicht, ohne fontconfig faellt nur die Schriftwahl auf eine
# Grundschrift zurueck - das eine ist ein Abbruch, das andere ein Schoenheits-
# fehler, deshalb die unterschiedliche Behandlung.
echo
meldung "[2/6] Pruefe Systempakete..." "$gelb"
if "$PYTHON" -c 'import tkinter' 2>/dev/null; then
    meldung "      OK: Tcl/Tk (tkinter)" "$gruen"
else
    meldung "FEHLER: tkinter fehlt. Bitte nachinstallieren:" "$rot"
    meldung "        Debian/Ubuntu:  sudo apt install python3-tk" "$rot"
    meldung "        Fedora:         sudo dnf install python3-tkinter" "$rot"
    meldung "        Arch:           sudo pacman -S tk" "$rot"
    exit 1
fi
if command -v fc-match >/dev/null 2>&1; then
    meldung "      OK: fontconfig ($(fc-match -f '%{family}' 'Segoe UI') als Flaechenschrift)" "$gruen"
else
    meldung "      WARNUNG: fontconfig fehlt - es wird die Tk-Grundschrift verwendet." "$gelb"
fi

# --- Schritt 3: Pakete installieren ---------------------------------------
echo
meldung "[3/6] Installiere/aktualisiere Abhaengigkeiten..." "$gelb"
"$PYTHON" -m pip install --upgrade pip --quiet

pflicht_installieren() {
    meldung "      $1 installieren/aktualisieren..." "$grau"
    if ! "$PYTHON" -m pip install "$1" --upgrade --quiet; then
        meldung "FEHLER: $1 konnte nicht installiert werden." "$rot"
        exit 1
    fi
}
optional_installieren() {
    meldung "      $1 installieren/aktualisieren (optional)..." "$grau"
    if ! "$PYTHON" -m pip install "$1" --upgrade --quiet; then
        meldung "WARNUNG: $1 fehlt - $2" "$gelb"
    fi
}

pflicht_installieren pyinstaller
pflicht_installieren pillow
pflicht_installieren cryptography
pflicht_installieren zstandard
optional_installieren zlib-ng "MkPFS nutzt die langsamere zlib der Standardbibliothek."
optional_installieren paramiko "kein SFTP."
optional_installieren tkinterdnd2 "kein Drag & Drop."
optional_installieren psutil "keine CPU/RAM-Telemetrie."
meldung "      PyInstaller $("$PYTHON" -m PyInstaller --version 2>&1) bereit." "$gruen"

# --- Schritt 4: Pflicht-Dateien pruefen -----------------------------------
echo
meldung "[4/6] Pruefe Pflicht-Dateien..." "$gelb"
fehlend=0
for datei in \
    "PS5ImageConverter_Pro_FINAL_revised.py" \
    "PS5ImageConverter_Pro_linux.spec" \
    "ps5_validator/utils/plattform.py" \
    "app_icon.ico"
do
    if [ -f "$datei" ]; then
        meldung "      OK: $datei" "$gruen"
    else
        meldung "      FEHLER: $datei fehlt!" "$rot"
        fehlend=$((fehlend + 1))
    fi
done

if [ -f "MkPFS-1.0.0/mkpfs/__init__.py" ]; then
    meldung "      OK: MkPFS-1.0.0/mkpfs/__init__.py" "$gruen"
else
    meldung "      FEHLER: MkPFS 1.0.0 fehlt (erwartet: MkPFS-1.0.0/mkpfs/__init__.py)" "$rot"
    fehlend=$((fehlend + 1))
fi

if [ "$fehlend" -gt 0 ]; then
    echo
    meldung "FEHLER: Pflicht-Dateien fehlen. Bitte den Quellordner vollstaendig bereitstellen." "$rot"
    exit 1
fi

if [ -d "helloworld" ]; then
    js_anzahl=$(find helloworld -maxdepth 1 -name '*.js' | wc -l)
    elf_anzahl=$(find helloworld -maxdepth 1 -name '*.elf' | wc -l)
    if [ $((js_anzahl + elf_anzahl)) -gt 0 ]; then
        meldung "      OK: helloworld/ ($js_anzahl JS, $elf_anzahl ELF Dateien)" "$gruen"
    else
        # Ein leerer Ordner wird von PyInstaller nicht eingebettet - die
        # Schnellauswahl im JS Loader bleibt dann leer.
        meldung "      WARNUNG: helloworld/ ist leer - JS Loader ohne Schnellzugriff" "$gelb"
    fi
else
    meldung "      WARNUNG: helloworld/ fehlt - JS Loader ohne Schnellzugriff" "$gelb"
fi

# --- Schritt 5: Alt-Artefakte bereinigen + Symbol synchronisieren ---------
echo
meldung "[5/6] Bereinige alte Build-Artefakte und synchronisiere das Symbol..." "$gelb"
# Gegenstueck zu extract_icon.py im Windows-Build: Der Menueeintrag braucht ein
# PNG, .ico zeigen die wenigsten Arbeitsumgebungen an. Ein Fehlschlag bricht den
# Bau nicht ab - das Symbol betrifft nur den Starter, nicht das Programm selbst.
if "$PYTHON" extract_icon_png.py; then
    meldung "      app_icon.png synchronisiert." "$gruen"
else
    meldung "      WARNUNG: app_icon.png nicht erzeugbar - der Starter bekommt ein Standardsymbol." "$gelb"
fi
# Nur den Linux-Build-Ordner anfassen: Ein gemeinsam genutzter Projektordner
# kann daneben das Ergebnis eines Windows-Builds enthalten.
if [ -d "build/${ZIELNAME}" ]; then
    rm -rf "build/${ZIELNAME}"
    meldung "      build/${ZIELNAME} entfernt." "$gruen"
else
    meldung "      build/ bereits sauber." "$grau"
fi
if [ -f "dist/$ZIELNAME" ]; then
    if ! rm -f "dist/$ZIELNAME"; then
        meldung "FEHLER: dist/$ZIELNAME nicht loeschbar. Laeuft das Programm noch?" "$rot"
        exit 1
    fi
    meldung "      Altes Programm entfernt: dist/$ZIELNAME" "$gruen"
else
    meldung "      Kein altes Programm im dist/-Ordner gefunden." "$grau"
fi

# --- Schritt 6: Programm erstellen ----------------------------------------
echo
meldung "[6/6] Erstelle Programmdatei (dauert 2-5 Minuten)..." "$gelb"
echo
if ! "$PYTHON" -m PyInstaller PS5ImageConverter_Pro_linux.spec --clean --noconfirm; then
    echo
    meldung "FEHLER: Erstellung fehlgeschlagen." "$rot"
    meldung "Tipp: Fehlermeldung oben lesen. Haeufige Ursachen:" "$gelb"
    meldung "  - Fehlende Systempakete: python3-tk, python3-dev" "$gelb"
    meldung "  - Fehlende pip-Pakete: pip install paramiko bcrypt" "$gelb"
    exit 1
fi

ERGEBNIS="dist/$ZIELNAME"
if [ ! -f "$ERGEBNIS" ]; then
    meldung "FEHLER: $ERGEBNIS wurde nicht erzeugt." "$rot"
    exit 1
fi
chmod +x "$ERGEBNIS"

# Der AMPR-/PlayGo-Ordner steckt wieder IM Programm (siehe .spec).
#
# Zwischenzeitlich lag er daneben, damit sich eine neue AMPR-Fassung
# hineinlegen laesst, ohne neu zu bauen. Das wiegt den Nachteil nicht auf: Wer
# das Programm weitergibt oder verschiebt und den Ordner vergisst, hat in
# Aufgabe 7 keine einzige Version zur Auswahl - ohne erkennbare Ursache.
#
# Ein eigener Ordner bleibt moeglich: Der AMPR-EMU-Manager hat dafuer eine
# Ordnerwahl, und --ampr-store tut auf der Kommandozeile dasselbe.
if [ ! -d "PlayGo & AMPR_EMU" ]; then
    meldung "      WARNUNG: 'PlayGo & AMPR_EMU' fehlt - Aufgabe 7 findet keine Versionen." "$gelb"
fi

# Ein danebenliegender Ordner aus einem frueheren Bau wuerde nur verwirren.
rm -rf "dist/PlayGo & AMPR_EMU"

echo
meldung "=============================================" "$gruen"
meldung "  BUILD ERFOLGREICH!" "$gruen"
meldung "=============================================" "$gruen"
echo
meldung "  Programm: $ERGEBNIS" "$blau"
meldung "  Groesse:  $(du -h "$ERGEBNIS" | cut -f1)" "$blau"
echo
meldung "  Start:            ./$ERGEBNIS" "$grau"
meldung "  Kommandozeile:    ./$ERGEBNIS --cli --help" "$grau"
meldung "  Ins Menue legen:  ./Install_Linux.sh" "$grau"
echo
meldung "  Hinweis: Aufgaben, die OSFMount, Dokan oder UFS2Tool brauchen," "$grau"
meldung "           laufen nur unter Windows. Das Programm sagt das beim" "$grau"
meldung "           Start einer solchen Aufgabe ausdruecklich." "$grau"
echo
