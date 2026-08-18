#!/usr/bin/env bash
# =============================================================================
# PS5 Dump & Image Converter - Menueeintrag unter Linux anlegen/entfernen
# =============================================================================
# Legt die gebaute Programmdatei, ihr Symbol und einen Starter im Anwendungs-
# menue ab - alles unterhalb von ~/.local, also ohne sudo und ohne Eingriff ins
# System.
#
#   ./Install_Linux.sh              installieren
#   ./Install_Linux.sh --entfernen  wieder entfernen
#
# Voraussetzung: ./Build_Linux.sh wurde vorher ausgefuehrt.
# =============================================================================
set -uo pipefail

cd "$(dirname "$(readlink -f "$0")")" || exit 1
PROJEKT="$PWD"

rot=$'\033[0;31m'; gruen=$'\033[0;32m'; gelb=$'\033[1;33m'
blau=$'\033[0;36m'; grau=$'\033[0;90m'; aus=$'\033[0m'
meldung() { printf '%s%s%s\n' "$2" "$1" "$aus"; }

ZIEL_BIN="$HOME/.local/bin"
ZIEL_APP="$HOME/.local/share/applications"
ZIEL_ICON="$HOME/.local/share/icons/hicolor/256x256/apps"
STARTER="$ZIEL_APP/ps5-dump-image-converter.desktop"
PROGRAMM="$ZIEL_BIN/ps5-dump-image-converter"
SYMBOL="$ZIEL_ICON/ps5-dump-image-converter.png"

# --- Entfernen -------------------------------------------------------------
if [ "${1:-}" = "--entfernen" ] || [ "${1:-}" = "--uninstall" ]; then
    meldung "Entferne Menueeintrag und Programmkopie..." "$gelb"
    for datei in "$STARTER" "$PROGRAMM" "$SYMBOL"; do
        if [ -e "$datei" ]; then
            rm -f "$datei" && meldung "  entfernt: $datei" "$gruen"
        else
            meldung "  nicht vorhanden: $datei" "$grau"
        fi
    done
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database "$ZIEL_APP" 2>/dev/null
    command -v gtk-update-icon-cache >/dev/null 2>&1 &&
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null
    echo
    meldung "Fertig. Die Einstellungen unter ~/.config/PS5ImageConverterPro bleiben erhalten." "$blau"
    meldung "Sie loeschen sie mit:  rm -rf ~/.config/PS5ImageConverterPro" "$grau"
    exit 0
fi

# --- Gebautes Programm finden ---------------------------------------------
# Neueste passende Datei nehmen: Nach mehreren Builds liegen im dist/-Ordner
# unter Umstaenden mehrere Versionsstaende.
QUELLE="$(find dist -maxdepth 1 -type f -name 'PS5_Dump_Image_Converter_*_linux_*' \
    -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"

if [ -z "$QUELLE" ]; then
    meldung "FEHLER: Keine gebaute Programmdatei in dist/ gefunden." "$rot"
    meldung "        Bitte zuerst ./Build_Linux.sh ausfuehren." "$rot"
    exit 1
fi

meldung "Gefunden: $QUELLE" "$blau"

# --- Symbol bereitstellen --------------------------------------------------
if [ ! -f "app_icon.png" ]; then
    meldung "app_icon.png fehlt - wird erzeugt..." "$gelb"
    PY="$PROJEKT/.venv-linux/bin/python"
    [ -x "$PY" ] || PY="$(command -v python3)"
    if [ -n "$PY" ]; then
        "$PY" extract_icon_png.py || true
    fi
fi

# --- Ablegen ---------------------------------------------------------------
mkdir -p "$ZIEL_BIN" "$ZIEL_APP" "$ZIEL_ICON"

install -m 755 "$QUELLE" "$PROGRAMM"
meldung "  Programm:  $PROGRAMM" "$gruen"

if [ -f "app_icon.png" ]; then
    install -m 644 "app_icon.png" "$SYMBOL"
    meldung "  Symbol:    $SYMBOL" "$gruen"
    ICON_NAME="ps5-dump-image-converter"
else
    meldung "  WARNUNG: Kein Symbol - der Starter bekommt ein Standardsymbol." "$gelb"
    ICON_NAME="application-x-executable"
fi

cat > "$STARTER" <<STARTEREOF
[Desktop Entry]
Type=Application
Version=1.0
Name=PS5 Dump & Image Converter
GenericName=PS5 Dump Converter
GenericName[de]=PS5-Dump-Konverter
Comment=Convert PS5 dumps between folder, .ffpfs, .ffpfsc and exFAT
Comment[de]=PS5-Dumps zwischen Ordner, .ffpfs, .ffpfsc und exFAT umwandeln
Exec=$PROGRAMM
Icon=$ICON_NAME
Terminal=false
Categories=Utility;Archiving;Compression;
Keywords=PS5;Dump;ffpfs;ffpfsc;ffpkg;exFAT;PKG;
StartupNotify=true
StartupWMClass=PS5ImageConverter_Pro_FINAL_revised
STARTEREOF
chmod 644 "$STARTER"
meldung "  Starter:   $STARTER" "$gruen"

command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database "$ZIEL_APP" 2>/dev/null
command -v gtk-update-icon-cache >/dev/null 2>&1 &&
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null

echo
meldung "=============================================" "$gruen"
meldung "  INSTALLATION ERFOLGREICH!" "$gruen"
meldung "=============================================" "$gruen"
echo
meldung "  Start ueber das Anwendungsmenue: \"PS5 Dump & Image Converter\"" "$blau"
meldung "  Start im Terminal:               ps5-dump-image-converter" "$blau"
echo
case ":$PATH:" in
    *":$ZIEL_BIN:"*) ;;
    *)
        meldung "  Hinweis: $ZIEL_BIN steht nicht in \$PATH." "$gelb"
        meldung "           Fuer den Terminalaufruf ergaenzen Sie in ~/.profile:" "$gelb"
        meldung "           export PATH=\"\$HOME/.local/bin:\$PATH\"" "$grau"
        echo
        ;;
esac
meldung "  Entfernen: ./Install_Linux.sh --entfernen" "$grau"
echo
