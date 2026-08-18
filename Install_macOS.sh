#!/usr/bin/env bash
# =============================================================================
# PS5 Dump & Image Converter - Programm unter macOS ablegen/entfernen
# =============================================================================
# Legt das gebaute Buendel in den Programme-Ordner. Ohne Schreibrecht auf
# /Applications wird der persoenliche Programme-Ordner (~/Applications)
# genommen - das braucht kein sudo und reicht fuer den Einzelplatz voellig.
#
#   ./Install_macOS.sh              installieren
#   ./Install_macOS.sh --entfernen  wieder entfernen
#
# Voraussetzung: ./Build_macOS.sh wurde vorher ausgefuehrt.
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")" || exit 1

rot=$'\033[0;31m'; gruen=$'\033[0;32m'; gelb=$'\033[1;33m'
blau=$'\033[0;36m'; grau=$'\033[0;90m'; aus=$'\033[0m'
meldung() { printf '%s%s%s\n' "$2" "$1" "$aus"; }

if [ "$(uname -s)" != "Darwin" ]; then
    meldung "FEHLER: Dieses Skript ist fuer macOS. Unter Linux: ./Install_Linux.sh" "$rot"
    exit 1
fi

BUENDELNAME="PS5 Dump & Image Converter.app"
QUELLE="dist/$BUENDELNAME"
EINSTELLUNGEN="$HOME/Library/Application Support/PS5ImageConverterPro"

# Zielordner waehlen: /Applications wenn beschreibbar, sonst ~/Applications.
if [ -w "/Applications" ]; then
    ZIELORDNER="/Applications"
else
    ZIELORDNER="$HOME/Applications"
fi
ZIEL="$ZIELORDNER/$BUENDELNAME"

# --- Entfernen -------------------------------------------------------------
if [ "${1:-}" = "--entfernen" ] || [ "${1:-}" = "--uninstall" ]; then
    meldung "Entferne das Programm..." "$gelb"
    entfernt=0
    for ordner in "/Applications/$BUENDELNAME" "$HOME/Applications/$BUENDELNAME"; do
        if [ -d "$ordner" ]; then
            if rm -rf "$ordner"; then
                meldung "  entfernt: $ordner" "$gruen"
                entfernt=$((entfernt + 1))
            else
                meldung "  FEHLER: $ordner nicht loeschbar (laeuft das Programm noch?)" "$rot"
            fi
        fi
    done
    [ "$entfernt" -eq 0 ] && meldung "  Nichts gefunden - war das Programm ueberhaupt abgelegt?" "$grau"
    echo
    meldung "Fertig. Die Einstellungen bleiben erhalten unter:" "$blau"
    meldung "  $EINSTELLUNGEN" "$grau"
    meldung "Sie loeschen sie mit:  rm -rf \"$EINSTELLUNGEN\"" "$grau"
    exit 0
fi

# --- Gebautes Buendel finden ----------------------------------------------
if [ ! -d "$QUELLE" ]; then
    meldung "FEHLER: $QUELLE nicht gefunden." "$rot"
    meldung "        Bitte zuerst ./Build_macOS.sh ausfuehren." "$rot"
    exit 1
fi

meldung "Gefunden: $QUELLE" "$blau"

# --- Ablegen ---------------------------------------------------------------
mkdir -p "$ZIELORDNER"

# Erst weg, dann hin: Ein 'cp' ueber ein vorhandenes Buendel laesst Dateien der
# alten Fassung stehen, die es in der neuen nicht mehr gibt. Bei einem
# signierten Buendel macht schon eine einzige solche Leiche die Signatur
# ungueltig, und das Programm startet nicht mehr.
if [ -d "$ZIEL" ]; then
    if ! rm -rf "$ZIEL"; then
        meldung "FEHLER: Vorherige Fassung nicht loeschbar: $ZIEL" "$rot"
        meldung "        Laeuft das Programm noch? Bitte beenden und erneut versuchen." "$rot"
        exit 1
    fi
    meldung "  vorherige Fassung entfernt" "$grau"
fi

# ditto statt cp: Es nimmt erweiterte Attribute und Ressourcengabeln
# zuverlaessig mit. Genau davon haengt die Signatur ab - ein Buendel, das beim
# Kopieren Metadaten verliert, gilt danach als beschaedigt und startet nicht.
# cp -R kann das auf aktuellen Systemen zwar auch, ditto ist dafuer aber das
# vorgesehene Werkzeug; der Rueckfall greift nur, falls es einmal fehlt.
if command -v ditto >/dev/null 2>&1; then
    kopierbefehl="ditto"
    ditto "$QUELLE" "$ZIEL"
else
    kopierbefehl="cp -R"
    cp -R "$QUELLE" "$ZIEL"
fi
if [ $? -ne 0 ] || [ ! -d "$ZIEL" ]; then
    meldung "FEHLER: Kopieren nach $ZIEL fehlgeschlagen ($kopierbefehl)." "$rot"
    exit 1
fi
meldung "  abgelegt:  $ZIEL" "$gruen"

# Quarantaene abraeumen, falls das Buendel ueber ein Archiv oder AirDrop kam:
# Sonst meldet macOS beim ersten Start "Programm kann nicht geoeffnet werden,
# da der Entwickler nicht ueberprueft werden kann".
xattr -dr com.apple.quarantine "$ZIEL" 2>/dev/null

# Die Signatur nach dem Kopieren pruefen, nicht davor: Ein beschaedigtes
# Buendel faellt sonst erst beim ersten Doppelklick auf.
if codesign --verify --deep --strict "$ZIEL" 2>/dev/null; then
    meldung "  Signatur:  geprueft" "$gruen"
else
    meldung "  WARNUNG: Die Signatur des abgelegten Buendels ist nicht in Ordnung." "$gelb"
    meldung "           Abhilfe: codesign --force --deep --sign - \"$ZIEL\"" "$grau"
fi

echo
meldung "=============================================" "$gruen"
meldung "  INSTALLATION ERFOLGREICH!" "$gruen"
meldung "=============================================" "$gruen"
echo
meldung "  Start ueber das Launchpad oder den Finder: \"PS5 Dump & Image Converter\"" "$blau"
meldung "  Start im Terminal:  open \"$ZIEL\"" "$blau"
meldung "  Kommandozeile:      \"$ZIEL/Contents/MacOS/PS5_Dump_Image_Converter\" --cli --help" "$grau"
echo
if [ "$ZIELORDNER" = "$HOME/Applications" ]; then
    meldung "  Hinweis: Abgelegt unter ~/Applications, weil /Applications nicht" "$gelb"
    meldung "           beschreibbar war. Das Launchpad zeigt das Programm trotzdem an." "$gelb"
    echo
fi
meldung "  Entfernen: ./Install_macOS.sh --entfernen" "$grau"
echo
