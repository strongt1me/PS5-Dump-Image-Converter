#!/usr/bin/env bash
# =============================================================================
# PS5 Dump & Image Converter - macOS Build-Skript
# =============================================================================
# Gegenstueck zu Build_EXE.ps1 (Windows) und Build_Linux.sh. Erzeugt ein
# Programmbuendel unter dist/.
#
# Aufruf:
#   chmod +x Build_macOS.sh
#   ./Build_macOS.sh            nur das Buendel
#   ./Build_macOS.sh --dmg      zusaetzlich ein Abbild zum Weitergeben
#
# Bewusst NICHT mit sudo starten: Zum Bauen braucht das Programm keine
# Root-Rechte, und ein als root gebautes dist/ gehoert danach root - der
# naechste Lauf als normaler Benutzer scheitert dann beim Aufraeumen.
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")" || exit 1
PROJEKT="$PWD"

rot=$'\033[0;31m'; gruen=$'\033[0;32m'; gelb=$'\033[1;33m'
blau=$'\033[0;36m'; grau=$'\033[0;90m'; aus=$'\033[0m'

meldung() { printf '%s%s%s\n' "$2" "$1" "$aus"; }

# Argumente ueber $# statt ueber "$@" abklappern: macOS liefert bis heute
# bash 3.2, und dort meldet "$@" zusammen mit 'set -u' einen Fehler, sobald das
# Skript ohne Argumente aufgerufen wird - also im Normalfall.
DMG_ERZEUGEN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --dmg) DMG_ERZEUGEN=1 ;;
        *)
            meldung "Unbekannter Schalter: $1" "$rot"
            meldung "Erlaubt ist nur --dmg." "$grau"
            exit 1
            ;;
    esac
    shift
done

if [ "$(uname -s)" != "Darwin" ]; then
    meldung "FEHLER: Dieses Skript baut das macOS-Buendel und laeuft nur auf einem Mac." "$rot"
    meldung "        Fuer Windows: Build_EXE.ps1      Fuer Linux: ./Build_Linux.sh" "$grau"
    exit 1
fi

VERSION="$(sed -n 's/^APP_VERSION[[:space:]]*=[[:space:]]*["'"'"']\(.*\)["'"'"'].*/\1/p' \
    PS5ImageConverter_Pro_FINAL_revised.py | head -1)"
VERSION="${VERSION:-unbekannt}"
ARCH="$(uname -m)"
BUENDEL="dist/PS5 Dump & Image Converter.app"
# Muss zum COLLECT-Namen in der .spec passen.
ROHORDNER="dist/PS5_Dump_Image_Converter_${VERSION}_macos_${ARCH}"

echo
meldung "=============================================" "$blau"
meldung "  PS5 Dump & Image Converter - macOS Build   " "$blau"
meldung "  Version: $VERSION   Architektur: $ARCH     " "$blau"
meldung "=============================================" "$blau"
echo

if [ "$(id -u)" -eq 0 ]; then
    meldung "WARNUNG: Als root gestartet. dist/ gehoert danach root." "$gelb"
    meldung "         Besser als normaler Benutzer bauen." "$gelb"
    echo
fi

# --- Schritt 1: Interpreter waehlen ---------------------------------------
# Bevorzugt der Projekt-Interpreter aus .venv-macos: Damit entstehen Programm
# und Testlaeufe auf derselben Python-Version. Die Windows-Umgebung heisst
# .venv, die Linux-Umgebung .venv-linux; ein eigener Name verhindert, dass sie
# sich auf einem gemeinsam genutzten Ordner gegenseitig ueberschreiben.
meldung "[1/7] Pruefe Python-Installation..." "$gelb"
VENV="$PROJEKT/.venv-macos"
if [ -x "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
else
    BASIS="$(command -v python3 || command -v python)"
    if [ -z "$BASIS" ]; then
        meldung "FEHLER: Python nicht gefunden." "$rot"
        meldung "        Empfohlen: python.org-Installer oder 'brew install python-tk'." "$rot"
        exit 1
    fi
    # Das von Apple mitgelieferte /usr/bin/python3 ist zum Bauen unbrauchbar:
    # Es bringt kein eigenes Tcl/Tk mit, und PyInstaller findet dort auch keine
    # Bibliothek zum Einbetten. Der Hinweis kommt hier statt erst beim Absturz.
    case "$BASIS" in
        /usr/bin/python3)
            meldung "FEHLER: Gefunden wurde nur Apples /usr/bin/python3." "$rot"
            meldung "        Damit laesst sich kein Buendel mit Oberflaeche bauen." "$rot"
            meldung "        Bitte Python von python.org installieren oder:" "$rot"
            meldung "          brew install python-tk" "$grau"
            exit 1
            ;;
    esac
    meldung "      Hinweis: .venv-macos fehlt - wird angelegt." "$gelb"
    if ! "$BASIS" -m venv "$VENV" 2>/dev/null; then
        meldung "FEHLER: Virtuelle Umgebung nicht anlegbar." "$rot"
        exit 1
    fi
    PYTHON="$VENV/bin/python"
fi
meldung "      Interpreter: $PYTHON" "$grau"
meldung "      $("$PYTHON" --version 2>&1) gefunden." "$gruen"

# --- Schritt 2: Tcl/Tk pruefen --------------------------------------------
# Unter macOS ist nicht nur das Vorhandensein von Tk entscheidend, sondern
# seine Version: Das systemeigene Tk 8.5 zeichnet Rahmen falsch, kennt kein
# dunkles Erscheinungsbild und stuerzt bei mehreren Fenstern reproduzierbar ab.
# Apple selbst raet seit Jahren davon ab. 8.6 ist Pflicht.
echo
meldung "[2/7] Pruefe Tcl/Tk..." "$gelb"
TKVERSION="$("$PYTHON" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null)"
if [ -z "$TKVERSION" ]; then
    meldung "FEHLER: tkinter fehlt in diesem Python." "$rot"
    meldung "        Abhilfe: Python von python.org installieren oder" "$rot"
    meldung "                 'brew install python-tk' und .venv-macos neu anlegen." "$rot"
    exit 1
fi
case "$TKVERSION" in
    8.6|8.7|9.*)
        meldung "      OK: Tcl/Tk $TKVERSION" "$gruen"
        ;;
    *)
        meldung "FEHLER: Tcl/Tk $TKVERSION ist zu alt (8.6 oder neuer noetig)." "$rot"
        meldung "        Das ist Apples altes System-Tk. Abhilfe:" "$rot"
        meldung "          Python von python.org installieren, dann .venv-macos loeschen" "$grau"
        meldung "          und dieses Skript erneut starten." "$grau"
        exit 1
        ;;
esac

# --- Schritt 3: Pakete installieren ---------------------------------------
echo
meldung "[3/7] Installiere/aktualisiere Abhaengigkeiten..." "$gelb"
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
meldung "[4/7] Pruefe Pflicht-Dateien..." "$gelb"
fehlend=0
for datei in \
    "PS5ImageConverter_Pro_FINAL_revised.py" \
    "PS5ImageConverter_Pro_macos.spec" \
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

if [ -f "MkPFS-0.0.9/mkpfs/__init__.py" ]; then
    meldung "      OK: MkPFS-0.0.9/mkpfs/__init__.py" "$gruen"
else
    meldung "      FEHLER: MkPFS 0.0.9 fehlt (erwartet: MkPFS-0.0.9/mkpfs/__init__.py)" "$rot"
    fehlend=$((fehlend + 1))
fi

if [ "$fehlend" -gt 0 ]; then
    echo
    meldung "FEHLER: Pflicht-Dateien fehlen. Bitte den Quellordner vollstaendig bereitstellen." "$rot"
    exit 1
fi

if [ -d "helloworld" ]; then
    js_anzahl=$(find helloworld -maxdepth 1 -name '*.js' | wc -l | tr -d ' ')
    elf_anzahl=$(find helloworld -maxdepth 1 -name '*.elf' | wc -l | tr -d ' ')
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

# --- Schritt 5: Symbol erzeugen + Alt-Artefakte bereinigen ----------------
echo
meldung "[5/7] Erzeuge das Symbol und bereinige alte Build-Artefakte..." "$gelb"
# Drittes Gegenstueck zu extract_icon.py (.ico) und extract_icon_png.py (.png):
# Der Finder zeigt nur .icns an. Ein Fehlschlag bricht den Bau nicht ab - ohne
# Symbol laeuft das Programm genauso, es sieht im Dock nur nackt aus.
if "$PYTHON" extract_icon_icns.py; then
    meldung "      app_icon.icns bereit." "$gruen"
else
    meldung "      WARNUNG: app_icon.icns nicht erzeugbar - das Buendel bekommt ein Standardsymbol." "$gelb"
fi
# Nur die macOS-Artefakte anfassen: Ein gemeinsam genutzter Projektordner kann
# daneben das Ergebnis eines Windows- oder Linux-Builds enthalten.
for alt in "build/$(basename "$ROHORDNER")" "$ROHORDNER" "$BUENDEL"; do
    if [ -e "$alt" ]; then
        if ! rm -rf "$alt"; then
            meldung "FEHLER: $alt nicht loeschbar. Laeuft das Programm noch?" "$rot"
            exit 1
        fi
        meldung "      entfernt: $alt" "$gruen"
    fi
done

# --- Schritt 6: Buendel erstellen -----------------------------------------
echo
meldung "[6/7] Erstelle das Programmbuendel (dauert 2-5 Minuten)..." "$gelb"
echo
if ! "$PYTHON" -m PyInstaller PS5ImageConverter_Pro_macos.spec --clean --noconfirm; then
    echo
    meldung "FEHLER: Erstellung fehlgeschlagen." "$rot"
    meldung "Tipp: Fehlermeldung oben lesen. Haeufige Ursachen:" "$gelb"
    meldung "  - Python ohne Tcl/Tk (siehe Schritt 2)" "$gelb"
    meldung "  - Ein Rad ohne passende Architektur (Intel-Rad auf Apple Silicon)" "$gelb"
    exit 1
fi

if [ ! -d "$BUENDEL" ]; then
    meldung "FEHLER: $BUENDEL wurde nicht erzeugt." "$rot"
    exit 1
fi

# --- Schritt 7: Signieren und pruefen -------------------------------------
echo
meldung "[7/7] Signiere das Buendel und pruefe es..." "$gelb"
# Reihenfolge beachten: erst aufraeumen, dann signieren. codesign legt die
# Signatur einzelner mitgelieferter Dateien in erweiterten Attributen ab - ein
# 'xattr -c' danach wuerde genau die wieder abraeumen und das eben signierte
# Buendel unbrauchbar machen. Frisch Gebautes traegt ohnehin keine Quarantaene;
# der Aufruf faengt nur Reste ab, etwa aus einem entpackten Archiv.
xattr -cr "$BUENDEL" 2>/dev/null

# Ad-hoc-Signatur ("-" statt eines Zertifikatsnamens). Auf Apple Silicon ist
# das keine Kuer: Dort verweigert das System jede unsignierte Programmdatei den
# Start. PyInstaller signiert zwar die einzelne Programmdatei, aber COLLECT
# legt danach noch Bibliotheken daneben - deshalb hier das fertige Buendel als
# Ganzes. --deep gilt bei Apple als veraltet, ist fuer eine Ad-hoc-Signatur
# ueber viele mitgelieferte .dylib-Dateien aber weiterhin der einzige Weg,
# der ohne Einzelaufruf je Datei auskommt.
if codesign --force --deep --sign - "$BUENDEL" 2>/dev/null; then
    if codesign --verify --deep --strict "$BUENDEL" 2>/dev/null; then
        meldung "      Ad-hoc-Signatur gesetzt und geprueft." "$gruen"
    else
        meldung "      WARNUNG: Signatur gesetzt, Pruefung meldet Beanstandungen." "$gelb"
    fi
else
    meldung "      WARNUNG: codesign fehlgeschlagen." "$gelb"
    meldung "               Auf Apple Silicon startet das Buendel dann moeglicherweise nicht." "$gelb"
    meldung "               Abhilfe: Xcode-Befehlszeilenwerkzeuge installieren:" "$grau"
    meldung "                 xcode-select --install" "$grau"
fi

GROESSE="$(du -sh "$BUENDEL" | cut -f1)"

# --- Optional: Abbild zum Weitergeben -------------------------------------
DMG=""
if [ "$DMG_ERZEUGEN" -eq 1 ]; then
    echo
    meldung "Erzeuge zusaetzlich ein Abbild (.dmg)..." "$gelb"
    DMG="dist/PS5_Dump_Image_Converter_${VERSION}_macos_${ARCH}.dmg"
    rm -f "$DMG"

    # Bis v1.8.58 wanderte allein das .app-Buendel ins Abbild. Wer es von
    # Hand nach /Applications zog, behielt die Quarantaene-Markierung - und
    # macOS blockierte den Start mit "nicht geoeffnet, Apple konnte nicht
    # ueberpruefen ...". Install_macOS.sh raeumt die Markierung ab (xattr
    # -dr com.apple.quarantine), lag aber nie im Abbild bei.
    #
    # Jetzt enthaelt das Abbild drei Dinge: das Buendel, den Installer als
    # doppelklickbare .command-Datei und eine Verknuepfung auf /Applications
    # fuer alle, die lieber ziehen.
    DMG_INHALT="$(mktemp -d)"
    ditto "$BUENDEL" "$DMG_INHALT/$(basename "$BUENDEL")"
    ln -s /Applications "$DMG_INHALT/Applications"

    KOMMANDO="$DMG_INHALT/Erste Installation.command"
    {
        echo '#!/bin/bash'
        echo '# Legt das Programm in den Programme-Ordner und raeumt die'
        echo '# Quarantaene-Markierung ab. Nur einmal noetig - danach startet'
        echo '# das Programm wie jedes andere.'
        echo 'cd "$(dirname "$0")" || exit 1'
        echo 'BUENDEL="PS5 Dump & Image Converter.app"'
        echo 'ZIEL="/Applications"'
        echo '[ -w "$ZIEL" ] || ZIEL="$HOME/Applications"'
        echo 'mkdir -p "$ZIEL"'
        echo 'echo "Kopiere nach $ZIEL ..."'
        echo 'rm -rf "$ZIEL/$BUENDEL"'
        echo 'ditto "$BUENDEL" "$ZIEL/$BUENDEL" || exit 1'
        echo 'xattr -dr com.apple.quarantine "$ZIEL/$BUENDEL" 2>/dev/null'
        echo 'echo "Fertig. Das Programm liegt in $ZIEL und startet ohne Warnung."'
        echo 'echo "Dieses Fenster kann geschlossen werden."'
    } > "$KOMMANDO"
    chmod +x "$KOMMANDO"

    # UDZO = komprimiertes, schreibgeschuetztes Abbild - das uebliche Format
    # zum Weitergeben eines Programms.
    #
    # Die Ausgabe von hdiutil ging bis v1.8.61 nach /dev/null. Als der Schritt
    # am 19.08.2026 auf dem Intel-Laeufer scheiterte, stand im Protokoll allein
    # "WARNUNG: Abbild nicht erzeugbar" - ohne Grund, ohne Fehlernummer, ohne
    # Anhaltspunkt. Auffallen tat es erst drei Schritte spaeter beim Hochladen
    # des Artefakts, und der Lauf galt trotzdem als erfolgreich.
    #
    # Deshalb: Ausgabe aufheben und bei Fehlschlag zeigen. Und einmal erneut
    # versuchen - Fehlschlaege beim Anlegen eines Abbilds auf einem
    # Bau-Laeufer sind haeufig voruebergehend (belegte Ressource, noch
    # eingehaengtes Volume aus einem frueheren Versuch).
    DMG_PROTOKOLL="$(mktemp)"
    dmg_versuch() {
        hdiutil create -volname "PS5 Dump & Image Converter" \
            -srcfolder "$DMG_INHALT" -ov -format UDZO "$DMG" >"$DMG_PROTOKOLL" 2>&1
    }

    if dmg_versuch; then
        meldung "      Abbild: $DMG ($(du -sh "$DMG" | cut -f1))" "$gruen"
    else
        meldung "      Abbild im ersten Anlauf nicht erzeugbar - hdiutil sagt:" "$gelb"
        sed 's/^/        /' "$DMG_PROTOKOLL"
        meldung "      Zweiter Versuch ..." "$gelb"
        sleep 5
        if dmg_versuch; then
            meldung "      Abbild: $DMG ($(du -sh "$DMG" | cut -f1))" "$gruen"
        else
            meldung "      FEHLER: Abbild nicht erzeugbar. hdiutil sagt:" "$rot"
            sed 's/^/        /' "$DMG_PROTOKOLL"
            rm -f "$DMG_PROTOKOLL"
            rm -rf "$DMG_INHALT"
            # Hier abbrechen statt weiterlaufen: Wer --dmg verlangt, will ein
            # Abbild. Ein "BUILD ERFOLGREICH" ohne das angeforderte Ergebnis
            # ist eine Falschmeldung.
            exit 1
        fi
    fi
    rm -f "$DMG_PROTOKOLL"
    rm -rf "$DMG_INHALT"
fi

echo
meldung "=============================================" "$gruen"
meldung "  BUILD ERFOLGREICH!" "$gruen"
meldung "=============================================" "$gruen"
echo
meldung "  Buendel:  $BUENDEL" "$blau"
meldung "  Groesse:  $GROESSE" "$blau"
[ -n "$DMG" ] && meldung "  Abbild:   $DMG" "$blau"
echo
meldung "  Start:            open \"$BUENDEL\"" "$grau"
meldung "  Kommandozeile:    \"$BUENDEL/Contents/MacOS/PS5_Dump_Image_Converter\" --cli --help" "$grau"
meldung "  In den Programme-Ordner legen:  ./Install_macOS.sh" "$grau"
echo
meldung "  Hinweis: Aufgaben, die OSFMount, Dokan oder UFS2Tool brauchen," "$grau"
meldung "           laufen nur unter Windows. Das Programm sagt das beim" "$grau"
meldung "           Start einer solchen Aufgabe ausdruecklich." "$grau"
echo
