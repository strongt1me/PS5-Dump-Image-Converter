# -*- coding: utf-8 -*-
"""Deutsche und neutrale Texte fuer die Oberflaeche von Direct Stream - ohne die Dateien des Werkzeugs zu aendern.

Die Oberflaeche des Werkzeugs (ChillQuant, MIT) ist englisch und spricht vom Mac. Das Programm liefert sie mit
einem zusaetzlichen Skript aus (:func:`skript`), das im Browser jeden Text und jede Beschriftung gegen dieses
Woerterbuch haelt und ersetzt - auch alles, was spaeter erscheint (Meldungen des Servers, Tabellenzeilen,
Rueckfragen ueber ``confirm``). Die Dateien in ``DirectStream-2.8.5/`` bleiben byte-gleich mit der Freigabe.

* **Deutsch** (Programm auf Deutsch): :data:`DEUTSCH` (ganze Texte), :data:`DEUTSCH_MUSTER` (Texte mit Zahlen oder
  Namen darin, als regulaere Ausdruecke) und :data:`DEUTSCH_TEILE` (Wortgruppen, die in vielen Texten vorkommen).
* **Englisch neutral** (sonst): nur :data:`NEUTRAL` - die Stellen, die vom Mac sprechen.

Ein Text, den das Woerterbuch nicht kennt, bleibt, wie er ist; ``test_direct_stream_texte.py`` meldet jeden
sichtbaren Text der Oberflaeche ohne Uebersetzung.
"""
from __future__ import annotations

import json
import re

#: Unter diesem Pfad liefert der Server das Skript aus (gleiche Herkunft - die Inhaltsrichtlinie erlaubt nur 'self').
SKRIPT_PFAD = "/ps5conv-texte.js"

#: Nur in der neutralen englischen Fassung: alles, was vom Mac spricht.
NEUTRAL: dict[str, str] = {
    "v2.8 · Pure Mac Native": "v2.8.5 · Pure Python",
    "Mac-to-PS5 local path": "Computer-to-PS5 local path",
    "Test the speed from your Mac to the console.": "Test the speed from this computer to the console.",
    "Connect both Mac and PS5 over Gigabit Ethernet to eliminate Wi-Fi interference.":
        "Connect both computer and PS5 over Gigabit Ethernet to eliminate Wi-Fi interference.",
    "/Users/you/Downloads/game.pkg": "…/Downloads/game.pkg",
    "Connection to the app was lost. Reopen DIRECT STREAM FOR PLAYSTATION 5 to reconnect.":
        "Connection to Direct Stream was lost. Press “8. Direct Stream” in the program to start it again.",
    'Launch DIRECT STREAM FOR PLAYSTATION 5 from its launcher (or run "ps5" in Termux) to connect.':
        "Press “8. Direct Stream” in the program to start it again.",
    "Quit DIRECT STREAM FOR PLAYSTATION 5? Closing the browser tab alone leaves the server running.":
        "Stop Direct Stream? Button “8. Direct Stream” in the program starts it again.",
    "DIRECT STREAM FOR PLAYSTATION 5 has stopped. You can close this tab.":
        "Direct Stream has stopped. Button “8. Direct Stream” in the program starts it again.",
    "Connection timed out. Check PS5 power, network, IP address, and Mac Local Network permission.":
        "Connection timed out. Check PS5 power, network and IP address.",
    "Local file was not found. Choose an existing file on this Mac.":
        "Local file was not found. Choose an existing file on this computer.",
    "This link does not provide stable resume metadata. Restart, or download to your Mac and send the local file.":
        "This link does not provide stable resume metadata. Restart, or download to this computer and send the local file.",
}

#: Ganze Texte (Leerraum zusammengefasst). Schluessel englisch, Wert deutsch.
DEUTSCH: dict[str, str] = {
    # --- Rahmen und Navigation ---
    "DIRECT STREAM FOR PLAYSTATION 5": "DIRECT STREAM FOR PLAYSTATION 5",
    "Transfer Files to PS5 Storage": "Dateien in den Speicher der PS5 übertragen",
    "Direct zero-copy stream over Gigabit LAN": "Direkt übers Netzwerk – ohne Zwischenspeichern",
    "Transfers": "Übertragungen",
    "Diagnostics": "Geschwindigkeit",
    "Console files": "Dateien auf der PS5",
    "Activity": "Verlauf",
    "Settings": "Einstellungen",
    "PS5 connected": "PS5 verbunden",
    "v2.8 · Pure Mac Native": "v2.8.5 · reines Python",
    "Quit app": "Beenden",
    "Connection to the app was lost. Reopen DIRECT STREAM FOR PLAYSTATION 5 to reconnect.":
        "Die Verbindung zu Direct Stream ist weg. Knopf „8. Direct Stream“ im Programm startet es wieder.",
    "Connected": "Verbunden",
    "Ready to stream": "Bereit",
    "Stream": "Senden",
    "Cancel": "Abbrechen",
    "Send games, packages and files to your PlayStation 5 over a high-speed local network.":
        "Spiele, Pakete und Dateien übers lokale Netzwerk auf die PlayStation 5 schicken.",
    "+ New transfer": "Neue Übertragung",
    "Idle": "Bereit",
    "Optimal path": "Bester Weg",
    "No active transfer": "Keine laufende Übertragung",
    "Queue is empty": "Warteschlange ist leer",
    "To console": "Zur PS5",
    "From source": "Von der Quelle",
    "RAM buffer": "Arbeitsspeicher-Puffer",
    "Now": "Jetzt",
    "Transfer queue": "Warteschlange",
    "Direct queue streaming · one FTP upload at a time": "Der Reihe nach · immer eine FTP-Übertragung",
    "Add files": "Dateien hinzufügen",
    "Add folder": "Ordner hinzufügen",
    "Add link": "Link hinzufügen",
    "Pause": "Anhalten",
    "Resume": "Fortsetzen",
    "Remove": "Entfernen",
    "Deselect": "Auswahl aufheben",
    "Name": "Name",
    "Size": "Größe",
    "Progress": "Fortschritt",
    "Status": "Zustand",
    "Actions": "Aktionen",
    "Queue is clear": "Warteschlange ist leer",
    "Paste a download link or drop package files anywhere to start streaming.":
        "Einen Download-Link einfügen oder Paketdateien ins Fenster ziehen, um zu beginnen.",
    "Add Transfer": "Übertragung hinzufügen",
    "Files verified byte-for-byte before atomic PS5 finalization":
        "Größe wird geprüft, bevor die Datei auf der PS5 ihren endgültigen Namen bekommt",
    "Start Queue": "Warteschlange starten",
    "Pause Queue": "Warteschlange anhalten",
    "Clear Completed": "Fertige entfernen",
    "Verify Links": "Links prüfen",
    # --- Geschwindigkeit ---
    "Find your fastest connection. Measure and optimize your download performance.":
        "Die schnellste Einstellung finden: Download-Geschwindigkeit messen und verbessern.",
    "Internet source benchmark": "Download-Quelle messen",
    "Test your download link with different stream and buffer presets.":
        "Den Download-Link mit verschiedenen Strom- und Puffervorgaben testen.",
    "Quick scan (~25s)": "Kurztest (~25 s)",
    "Full test (~60s)": "Volltest (~60 s)",
    "Run Quick Scan": "Kurztest starten",
    "Run Full Test": "Volltest starten",
    "Stop": "Stopp",
    "Single test": "Einzeltest",
    "— MB/s": "— MB/s",
    "Sustained download rate": "Dauerhafte Download-Rate",
    "Apply Recommended Settings": "Empfohlene Einstellung übernehmen",
    "Mac-to-PS5 local path": "Vom Rechner zur PS5",
    "Test the speed from your Mac to the console.": "Die Geschwindigkeit von diesem Rechner zur Konsole testen.",
    "Choose a file...": "Datei wählen …",
    "Choose a folder...": "Ordner wählen …",
    "Sustained upload rate": "Dauerhafte Übertragungsrate",
    "Wired connection recommended": "Kabelverbindung empfohlen",
    "Your network is performing well. A wired connection will provide the most consistent results.":
        "Das Netzwerk arbeitet gut. Eine Kabelverbindung liefert die gleichmäßigsten Ergebnisse.",
    "Optimal preset": "Beste Vorgabe",
    "Parallel workers": "Gleichzeitige Ströme",
    "Understand your results": "Die Ergebnisse verstehen",
    "Ethernet Link": "Kabelverbindung",
    "Connect both Mac and PS5 over Gigabit Ethernet to eliminate Wi-Fi interference.":
        "Rechner und PS5 per Gigabit-Ethernet verbinden, dann stört kein WLAN.",
    "Parallel Streams": "Gleichzeitige Ströme",
    "16 parallel HTTP streams overcome ISP TCP window limits on single connections.":
        "16 gleichzeitige HTTP-Ströme umgehen die Grenzen einzelner Verbindungen beim Anbieter.",
    "Decoupled Buffer": "Getrennter Puffer",
    "256 MiB RAM buffer prevents stalls when source download rate fluctuates.":
        "256 MiB Puffer im Arbeitsspeicher verhindern Stocken, wenn die Download-Rate schwankt.",
    # --- Dateien auf der PS5 ---
    "Browse your PS5 storage. This view is read-only while transfers are paused.":
        "Den Speicher der PS5 durchsehen. Hier wird nur gelesen, solange Übertragungen angehalten sind.",
    "of": "von",
    "Go": "Öffnen",
    "↑ Parent": "↑ Übergeordnet",
    "Read-only connection active.": "Verbindung nur zum Lesen.",
    "Type": "Art",
    "Modified": "Geändert",
    "Click Refresh or enter a directory above to explore PS5 storage.":
        "Auf Aktualisieren klicken oder oben einen Ordner eingeben, um den Speicher der PS5 zu durchsehen.",
    "Browsing is read-only. Files can be added via the Transfers page.":
        "Hier wird nur gelesen. Dateien kommen über die Seite „Übertragungen“ hinzu.",
    "Folder": "Ordner",
    "Package": "Paket",
    "Partial": "Unvollständig",
    "File": "Datei",
    "Copy": "Kopieren",
    "Copy remote path": "Pfad auf der PS5 kopieren",
    # --- Verlauf ---
    "View a log of transfers, connections and system activity.":
        "Protokoll der Übertragungen, Verbindungen und Systemmeldungen.",
    "Export log": "Protokoll speichern",
    "transfers completed": "Übertragungen fertig",
    "errors": "Fehler",
    "connections": "Verbindungen",
    "events": "Ereignisse",
    "All (": "Alle (",
    "Transfers (": "Übertragungen (",
    "Connections (": "Verbindungen (",
    "Errors (": "Fehler (",
    "Time": "Zeit",
    "Message": "Meldung",
    "System": "System",
    "Transfer": "Übertragung",
    # --- Einstellungen ---
    "Configure your console connection and transfer preferences.":
        "Verbindung zur Konsole und Übertragung einstellen.",
    "All Settings": "Alle Einstellungen",
    "Connection": "Verbindung",
    "Transfer Engine": "Übertragung",
    "Console connection": "Verbindung zur Konsole",
    "Console address": "Adresse der PS5",
    "Port": "Port",
    "Destination directory": "Zielordner auf der PS5",
    "Test connection": "Verbindung testen",
    "Checking…": "Prüfe …",
    "Connecting to console": "Verbinde mit der Konsole",
    "Transfer engine": "Übertragung",
    "Fine-tune parallel workers, RAM caching, and socket throughput.":
        "Gleichzeitige Ströme, Puffer im Arbeitsspeicher und Durchsatz feinabstimmen.",
    "Presets:": "Vorgaben:",
    "Conservative": "Vorsichtig",
    "Balanced": "Ausgewogen",
    "Turbo": "Turbo",
    "Max Saturation": "Maximum",
    "Parallel streams": "Gleichzeitige Ströme",
    "1 stream (Single stream / No range)": "1 Strom (einzeln / ohne Bereiche)",
    "2 streams (Low-Bandwidth / Wi-Fi)": "2 Ströme (langsame Leitung / WLAN)",
    "4 streams (Standard Entry Broadband)": "4 Ströme (einfacher Breitbandanschluss)",
    "6 streams (Stable Mid-Bandwidth)": "6 Ströme (mittlere Leitung)",
    "8 streams (Balanced Default)": "8 Ströme (ausgewogene Vorgabe)",
    "12 streams (High-Speed Fiber)": "12 Ströme (schnelle Glasfaser)",
    "16 streams (Fast Turbo / Recommended)": "16 Ströme (Turbo / empfohlen)",
    "24 streams (Ultra Fiber)": "24 Ströme (sehr schnelle Glasfaser)",
    "32 streams (Max LAN Saturation)": "32 Ströme (Netzwerk ausreizen)",
    "Concurrent HTTP range requests.": "Gleichzeitige HTTP-Bereichsabfragen.",
    "Chunk slice size": "Stückgröße",
    "2 MiB (Low-Bandwidth / Wi-Fi)": "2 MiB (langsame Leitung / WLAN)",
    "4 MiB (Standard Entry Broadband)": "4 MiB (einfacher Breitbandanschluss)",
    "8 MiB (Balanced / Recommended)": "8 MiB (ausgewogen / empfohlen)",
    "16 MiB (Ultra-Wide Pipeline)": "16 MiB (breite Leitung)",
    "32 MiB (Max Saturation)": "32 MiB (Maximum)",
    "Size of each downloaded segment.": "Größe jedes geladenen Stücks.",
    "32 MiB (Wi-Fi Tier)": "32 MiB (WLAN)",
    "64 MiB (Standard Entry)": "64 MiB (einfach)",
    "96 MiB (Stable Mid-Bandwidth)": "96 MiB (mittlere Leitung)",
    "128 MiB (Balanced Default)": "128 MiB (ausgewogene Vorgabe)",
    "192 MiB (High-Speed Fiber)": "192 MiB (schnelle Glasfaser)",
    "256 MiB (Fast Turbo / Recommended)": "256 MiB (Turbo / empfohlen)",
    "384 MiB (Ultra-Wide Pipeline)": "384 MiB (breite Leitung)",
    "512 MiB (Max Saturation)": "512 MiB (Maximum)",
    "1024 MiB (1 GB High-Memory)": "1024 MiB (1 GB, viel Arbeitsspeicher)",
    "Memory ring buffer preventing pipeline stalls.": "Puffer im Arbeitsspeicher gegen Stocken.",
    "Speed cap (MB/s)": "Höchstgeschwindigkeit (MB/s)",
    "0 = Unlimited LAN/WAN bandwidth.": "0 = unbegrenzt.",
    "Network retries": "Wiederholungen bei Netzfehlern",
    "0 (Fail immediately)": "0 (sofort abbrechen)",
    "1 retry": "1 Wiederholung",
    "2 retries": "2 Wiederholungen",
    "3 retries (Recommended)": "3 Wiederholungen (empfohlen)",
    "5 retries": "5 Wiederholungen",
    "Auto-reconnect with exponential backoff.": "Neu verbinden mit wachsender Wartezeit.",
    "Pipeline capacity": "Pufferbedarf",
    "Buffer must be ≥ streams × chunk size.": "Der Puffer muss mindestens Ströme × Stückgröße fassen.",
    "Verify files after transfer": "Dateien nach der Übertragung prüfen",
    "Always verifies final PS5 remote file size matches source before completing.":
        "Prüft immer, ob die Größe auf der PS5 der Quelle entspricht, bevor die Datei fertig ist.",
    "Reset to defaults": "Vorgaben wiederherstellen",
    "Save changes": "Änderungen speichern",
    "PRECISION STREAMING ARCHITECTURE": "PRÄZISE ÜBERTRAGUNG",
    "A quieter kind of performance.": "Leise und schnell.",
    "FTP Password (optional)": "FTP-Kennwort (wahlweise)",
    "Save settings": "Einstellungen speichern",
    # --- Neue Uebertragung ---
    "New transfer": "Neue Übertragung",
    "Add a file, folder or download link to your transfer queue.":
        "Eine Datei, einen Ordner oder einen Download-Link zur Warteschlange hinzufügen.",
    "Link": "Link",
    "Direct download URL": "Direkter Download-Link",
    "Local package path": "Pfad der Datei auf diesem Rechner",
    "Browse file": "Datei wählen",
    "Browse folder": "Ordner wählen",
    "Destination on PS5": "Ziel auf der PS5",
    "Browse": "Wählen",
    "No package selected": "Keine Datei gewählt",
    "Enter URL or choose local package": "Link eingeben oder Datei wählen",
    "Change": "Ändern",
    "Advanced options": "Weitere Optionen",
    "Custom destination filename": "Eigener Dateiname auf der PS5",
    "Allow replacement of existing console file on size match": "Vorhandene Datei auf der PS5 ersetzen dürfen",
    "Add to queue": "Zur Warteschlange",
    "Update Download Link": "Download-Link erneuern",
    "Replace expired direct URL with a fresh one.": "Einen abgelaufenen Link durch einen neuen ersetzen.",
    "Fresh direct link": "Neuer direkter Link",
    "Must point to the exact same file. Size and validators are re-checked before resuming.":
        "Muss genau dieselbe Datei meinen. Größe und Kennzeichen werden vor dem Fortsetzen erneut geprüft.",
    "Update link": "Link erneuern",
    # --- Beschriftungen (title, aria-label, placeholder) ---
    "DIRECT STREAM FOR PLAYSTATION 5 home": "DIRECT STREAM FOR PLAYSTATION 5 – Start",
    "Main navigation": "Hauptnavigation",
    "Click to view console connection settings": "Klicken: Einstellungen der Verbindung zur PS5",
    "Mobile navigation header": "Navigation",
    "Pause or Resume transfer": "Übertragung anhalten oder fortsetzen",
    "Pause transfer": "Übertragung anhalten",
    "Active transfer progress": "Fortschritt der laufenden Übertragung",
    "Real-time speed telemetry graph": "Geschwindigkeit in Echtzeit",
    "Select all jobs": "Alle Aufträge wählen",
    "Verify HTTP direct links without downloading": "Links prüfen, ohne herunterzuladen",
    "Benchmark scan type": "Art der Messung",
    "Back": "Zurück",
    "Forward": "Vor",
    "Search files...": "Dateien suchen …",
    "Refresh files list": "Dateiliste aktualisieren",
    "Search activity...": "Verlauf durchsuchen …",
    "Settings categories": "Bereiche der Einstellungen",
    "Performance presets": "Vorgaben",
    "Always verify final PS5 remote file size": "Größe auf der PS5 immer prüfen",
    "Close new transfer": "Neue Übertragung schließen",
    "Transfer source type": "Art der Quelle",
    "/Users/you/Downloads/game.pkg": "…\\Downloads\\spiel.pkg",
    "Auto-detected from source filename": "Wird aus dem Dateinamen der Quelle übernommen",
    "Close settings": "Einstellungen schließen",
    "Leave empty for anonymous": "Leer lassen für anonym",
    "Close update link": "Link erneuern schließen",
    # --- Meldungen aus app.js ---
    "Unknown size": "Größe unbekannt",
    "Move up ↑": "Nach oben ↑",
    "Move down ↓": "Nach unten ↓",
    "Restart from zero": "Von vorn beginnen",
    "Cancel transfer": "Übertragung abbrechen",
    "Remove from queue": "Aus der Warteschlange entfernen",
    "Transferring": "Überträgt",
    "Verified": "Geprüft",
    "Not configured": "Nicht eingerichtet",
    "Offline": "Getrennt",
    "Add your PS5 address": "PS5-Adresse eintragen",
    "Disconnected": "Getrennt",
    "PS5 ready for transfers": "PS5 bereit",
    "Check IP and network": "Adresse und Netzwerk prüfen",
    "Local file · zero RAM copy": "Lokale Datei · ohne Zwischenspeicher",
    "Direct stream · async buffers": "Direkt · gepuffert",
    "Resume transfer": "Übertragung fortsetzen",
    "Queued": "Wartet",
    "Ready to start": "Bereit zum Start",
    "Paused": "Angehalten",
    "All transfers completed": "Alle Übertragungen fertig",
    "Your queue is ready. Press Start queue to stream.": "Die Warteschlange ist bereit. „Warteschlange starten“ beginnt.",
    "Paste a download link above or drag package files directly onto this window.":
        "Oben einen Download-Link einfügen oder Paketdateien ins Fenster ziehen.",
    "Queue stopped after an error. Review the failed job.":
        "Die Warteschlange hat nach einem Fehler angehalten. Den fehlgeschlagenen Auftrag ansehen.",
    "Add files now. Send them in order.": "Gesendet wird der Reihe nach.",
    "Testing…": "Teste …",
    "No activity matches the current view.": "Keine Einträge in dieser Ansicht.",
    'Launch DIRECT STREAM FOR PLAYSTATION 5 from its launcher (or run "ps5" in Termux) to connect.':
        "Knopf „8. Direct Stream“ im Programm startet es wieder.",
    "Start from zero in a new partial file? The old partial stays on PS5 and may use disk space.":
        "In einer neuen Teildatei von vorn beginnen? Die alte Teildatei bleibt auf der PS5 und belegt weiter Platz.",
    "Remove this job? Its partial file will remain on PS5, and this app will no longer have its resume history.":
        "Diesen Auftrag entfernen? Seine Teildatei bleibt auf der PS5, fortsetzen lässt er sich danach nicht mehr.",
    "Cancel this transfer? Any partial file will stay on PS5.":
        "Diese Übertragung abbrechen? Eine Teildatei bleibt auf der PS5.",
    "Queued. Press Start queue to begin if the queue is paused.":
        "In der Warteschlange. Ist sie angehalten, beginnt „Warteschlange starten“.",
    "Direct download link · Package file": "Direkter Download-Link · Paketdatei",
    "Direct link": "Direkter Link",
    "Local file · Ready to stream": "Lokale Datei · bereit",
    "Leave Save as blank when adding multiple links.": "Bei mehreren Links den Dateinamen leer lassen.",
    "Settings saved": "Einstellungen gespeichert",
    "Settings reset to recommended defaults (16 streams · 8 MiB chunk · 256 MiB RAM)":
        "Einstellungen auf die empfohlenen Vorgaben gesetzt (16 Ströme · 8 MiB je Stück · 256 MiB Puffer)",
    "Download link updated": "Download-Link erneuert",
    "File picker dialog not available in terminal/mobile mode. Enter or paste the file path directly.":
        "Der Dateidialog ist hier nicht verfügbar. Den Pfad bitte eingeben oder einfügen.",
    "Folder picker dialog not available in terminal/mobile mode. Enter or paste the folder path directly.":
        "Der Ordnerdialog ist hier nicht verfügbar. Den Pfad bitte eingeben oder einfügen.",
    "Enter": "Eingeben",
    "Validating queued download links…": "Prüfe die Download-Links der Warteschlange …",
    "Paused selected transfers": "Gewählte Übertragungen angehalten",
    "Resumed selected transfers": "Gewählte Übertragungen fortgesetzt",
    "Removed selected transfers": "Gewählte Übertragungen entfernt",
    "Applied Conservative preset (4 streams · 4 MiB chunk · 64 MiB RAM)":
        "Vorgabe „Vorsichtig“ übernommen (4 Ströme · 4 MiB je Stück · 64 MiB Puffer)",
    "Applied Balanced preset (8 streams · 8 MiB chunk · 128 MiB RAM)":
        "Vorgabe „Ausgewogen“ übernommen (8 Ströme · 8 MiB je Stück · 128 MiB Puffer)",
    "Applied Turbo preset (16 streams · 8 MiB chunk · 256 MiB RAM)":
        "Vorgabe „Turbo“ übernommen (16 Ströme · 8 MiB je Stück · 256 MiB Puffer)",
    "Applied Max Saturation preset (16 streams · 32 MiB chunk · 512 MiB RAM)":
        "Vorgabe „Maximum“ übernommen (16 Ströme · 32 MiB je Stück · 512 MiB Puffer)",
    "No matching files found.": "Keine passenden Dateien.",
    "No files in this directory.": "Keine Dateien in diesem Ordner.",
    "PlayStation 5 notification chimes enabled": "Hinweistöne an",
    "Chimes muted": "Hinweistöne aus",
    "Pause the active transfer and quit DIRECT STREAM FOR PLAYSTATION 5? Partial data will remain on PS5.":
        "Die laufende Übertragung anhalten und Direct Stream beenden? Die Teildatei bleibt auf der PS5.",
    "Quit DIRECT STREAM FOR PLAYSTATION 5? Closing the browser tab alone leaves the server running.":
        "Direct Stream beenden? Knopf „8. Direct Stream“ im Programm startet es wieder.",
    "DIRECT STREAM FOR PLAYSTATION 5 has stopped. You can close this tab.":
        "Direct Stream ist beendet. Knopf „8. Direct Stream“ im Programm startet es wieder.",
    "Files": "Dateien",
    "Optimal": "Beste",
    # --- Meldungen des Servers (ps5_streamer.py, transfer_core.py) ---
    "Enter a PS5 IP address or hostname, without a URL or port.":
        "Eine IP-Adresse oder einen Rechnernamen der PS5 eingeben – ohne Link und ohne Port.",
    "Speed cap must be 0–1000 MB/s; 0 means unlimited.":
        "Die Höchstgeschwindigkeit muss zwischen 0 und 1000 MB/s liegen; 0 heißt unbegrenzt.",
    "RAM buffer must be at least streams × chunk size (for example, 8 × 8 = 64 MiB).":
        "Der Puffer muss mindestens Ströme × Stückgröße fassen (zum Beispiel 8 × 8 = 64 MiB).",
    "PS5 refused the connection. Check the FTP payload is running and the port is correct.":
        "Die PS5 lehnt die Verbindung ab. Läuft der FTP-Server auf der Konsole, und stimmt der Port?",
    "Connection timed out. Check PS5 power, network, IP address, and Mac Local Network permission.":
        "Zeitüberschreitung. Ist die PS5 an, das Netzwerk in Ordnung und die Adresse richtig?",
    "FTP refused the operation. Check login, folder permissions, and payload compatibility.":
        "Der FTP-Server lehnt ab. Anmeldung, Ordnerrechte und FTP-Payload prüfen.",
    "Could not resolve the download host name (DNS). Check the link and your internet/VPN/DNS.":
        "Der Rechnername des Downloads ließ sich nicht auflösen (DNS). Link und Internetverbindung prüfen.",
    "Connection was reset mid-transfer (by the download server, your network, or the PS5).":
        "Die Verbindung brach mitten in der Übertragung ab (Download-Server, Netzwerk oder PS5).",
    "Add your PS5 address to connect": "PS5-Adresse eintragen, um zu verbinden",
    "Restored after app restart. Resume when ready.": "Nach dem Neustart wiederhergestellt. Fortsetzen, wenn bereit.",
    "Saved queue could not be loaded. The original state file is retained until you make changes.":
        "Die gespeicherte Warteschlange ließ sich nicht laden. Die Datei bleibt erhalten, bis etwas geändert wird.",
    "Pause transfers and finish diagnostics before changing settings.":
        "Vor dem Ändern der Einstellungen Übertragungen anhalten und Messungen beenden.",
    "Settings saved · test the connection": "Einstellungen gespeichert · Verbindung testen",
    "Choose a direct link or a local file.": "Einen direkten Link oder eine lokale Datei wählen.",
    "Add between 1 and 100 files at a time.": "Bitte 1 bis 100 Dateien auf einmal hinzufügen.",
    "Local file not found. Use Choose file or enter its full path.":
        "Lokale Datei nicht gefunden. „Datei wählen“ benutzen oder den ganzen Pfad eingeben.",
    "Waiting to start": "Wartet auf den Start",
    "Queue is full. Clear completed jobs first.": "Die Warteschlange ist voll. Zuerst fertige Aufträge entfernen.",
    "Save your PS5 IP address in Settings first.": "Zuerst die PS5-Adresse in den Einstellungen speichern.",
    "Wait for the diagnostic to finish, or stop it first.": "Die Messung abwarten oder zuerst stoppen.",
    "Stopping network activity; partial file will be retained": "Halte an; die Teildatei bleibt erhalten",
    "Job no longer exists.": "Den Auftrag gibt es nicht mehr.",
    "Cannot move the active transfer.": "Die laufende Übertragung lässt sich nicht verschieben.",
    "Queued to resume": "Wartet aufs Fortsetzen",
    "Pause the active transfer before removing it.": "Die laufende Übertragung vor dem Entfernen anhalten.",
    "Link validation started in background": "Linkprüfung läuft im Hintergrund",
    "Partial file retained on PS5, if any": "Eine Teildatei bleibt auf der PS5, falls vorhanden",
    "Wait for the current operation to stop.": "Warten, bis der laufende Vorgang angehalten hat.",
    "This job is already complete.": "Dieser Auftrag ist schon fertig.",
    "Queued to restart from zero; old partial retained": "Beginnt von vorn; die alte Teildatei bleibt",
    "Pause the job before removing it.": "Den Auftrag vor dem Entfernen anhalten.",
    "Unknown queue action.": "Unbekannte Aktion.",
    "Parallel ranges OK": "Gleichzeitige Bereiche möglich",
    "Single-stream only": "Nur ein Strom möglich",
    "Link validation finished.": "Linkprüfung fertig.",
    "Pause a URL job before updating its link.": "Den Auftrag vor dem Erneuern des Links anhalten.",
    "Link updated. Source identity will be checked before resume.":
        "Link erneuert. Vor dem Fortsetzen wird geprüft, ob es dieselbe Datei ist.",
    "Complete · PS5 file size verified": "Fertig · Größe auf der PS5 geprüft",
    "PS5 destination changed. Restore the original settings to resume, or Restart for this destination.":
        "Das Ziel auf der PS5 hat sich geändert. Die alten Einstellungen wiederherstellen oder für das neue Ziel von vorn beginnen.",
    "Stopped · partial retained on PS5; resume checks its actual size":
        "Angehalten · die Teildatei bleibt auf der PS5; Fortsetzen prüft ihre Größe",
    "Pause the queue before running a diagnostic.": "Vor einer Messung die Warteschlange anhalten.",
    "Unknown diagnostic.": "Unbekannte Messung.",
    "Save your PS5 address in Settings first.": "Zuerst die PS5-Adresse in den Einstellungen speichern.",
    "Single stream (server has no range support)": "Ein Strom (der Server kann keine Bereiche)",
    "Cannot open this folder. Check that it exists and is readable.":
        "Der Ordner lässt sich nicht öffnen. Gibt es ihn, und ist er lesbar?",
    "Folder has over 2,000 entries. Open a smaller subfolder.":
        "Der Ordner hat über 2.000 Einträge. Bitte einen kleineren Unterordner öffnen.",
    "Folder listing is too large. Open a smaller subfolder.":
        "Die Liste ist zu groß. Bitte einen kleineren Unterordner öffnen.",
    "Diagnostic stopped": "Messung gestoppt",
    "Invalid host": "Ungültiger Rechnername",
    "Invalid file name.": "Ungültiger Dateiname.",
    "Invalid destination folder.": "Ungültiger Zielordner.",
    "Invalid download URL.": "Ungültiger Download-Link.",
    "Invalid local path.": "Ungültiger lokaler Pfad.",
    "Invalid local file path.": "Ungültiger Pfad der lokalen Datei.",
    "Invalid FTP username.": "Ungültiger FTP-Benutzername.",
    "Invalid FTP password.": "Ungültiges FTP-Kennwort.",
    "Cross-origin requests are not allowed": "Anfragen von fremden Seiten sind nicht erlaubt",
    "This app session expired. Reopen the app.":
        "Die Sitzung ist abgelaufen. Knopf „8. Direct Stream“ im Programm erneut drücken.",
    "Not found": "Nicht gefunden",
    "Expected a JSON request.": "Erwartet wurde eine JSON-Anfrage.",
    "Invalid request size.": "Ungültige Anfragegröße.",
    "Invalid request.": "Ungültige Anfrage.",
    "Invalid request. Check the fields and try again.": "Ungültige Anfrage. Bitte die Felder prüfen.",
    "Use a file name without slashes or control characters.": "Bitte einen Dateinamen ohne Schrägstriche oder Steuerzeichen.",
    "Destination must be an absolute PS5 folder without '..'.":
        "Das Ziel muss ein vollständiger Ordner auf der PS5 sein, ohne „..“.",
    "Use an HTTP or HTTPS direct link (URL-encode spaces and non-ASCII characters).":
        "Bitte einen direkten HTTP- oder HTTPS-Link (Leerzeichen und Sonderzeichen codiert).",
    "Blocked an HTTPS-to-HTTP redirect. Use a secure direct link.":
        "Weiterleitung von HTTPS auf HTTP blockiert. Bitte einen sicheren direkten Link verwenden.",
    "The download server sent an invalid Content-Range.": "Der Download-Server schickte einen ungültigen Bereich.",
    "The download server returned the wrong byte range; transfer stopped to protect the file.":
        "Der Download-Server lieferte den falschen Bereich; die Übertragung wurde zum Schutz der Datei gestoppt.",
    "Compressed range responses cannot be safely assembled.":
        "Komprimierte Bereichsantworten lassen sich nicht sicher zusammensetzen.",
    "Local file was not found. Choose an existing file on this Mac.":
        "Lokale Datei nicht gefunden. Bitte eine vorhandene Datei auf diesem Rechner wählen.",
    "This is a web page, not a downloadable file. Paste the direct download link.":
        "Das ist eine Webseite, keine Datei. Bitte den direkten Download-Link einfügen.",
    "Server ignored the request for uncompressed bytes.": "Der Server liefert nur komprimiert.",
    "Temporary HTTP error or source rate limit": "Vorübergehender HTTP-Fehler oder Begrenzung der Quelle",
    "Source ETag changed during transfer.": "Die Quelle hat sich während der Übertragung geändert (ETag).",
    "Source modification date changed during transfer.": "Die Quelle hat sich während der Übertragung geändert (Datum).",
    "Download ended before the requested range was complete.": "Der Download endete vor dem Ende des Bereichs.",
    "Server returned more bytes than requested.": "Der Server lieferte mehr als angefragt.",
    "Server ignored resume. Stopped before appending incorrect bytes.":
        "Der Server kann nicht fortsetzen. Gestoppt, bevor falsche Daten angehängt werden.",
    "Expected a complete HTTP response.": "Erwartet wurde eine vollständige HTTP-Antwort.",
    "Source ETag changed before the download started.": "Die Quelle hat sich vor dem Download geändert (ETag).",
    "Source modification date changed before download.": "Die Quelle hat sich vor dem Download geändert (Datum).",
    "Source length changed before the download started.": "Die Größe der Quelle hat sich vor dem Download geändert.",
    "Server returned a web page or compressed bytes.": "Der Server lieferte eine Webseite oder komprimierte Daten.",
    "Source ended early; partial file retained.": "Die Quelle endete zu früh; die Teildatei bleibt erhalten.",
    "Source length changed while reading.": "Die Größe der Quelle hat sich beim Lesen geändert.",
    "PS5 FTP did not return a file size.": "Der FTP-Server der PS5 nannte keine Dateigröße.",
    "PS5 FTP must support SIZE for safe transfers and resume.":
        "Der FTP-Server der PS5 muss SIZE können – sonst gibt es kein sicheres Übertragen und Fortsetzen.",
    "Inspecting source": "Prüfe die Quelle",
    "Source changed since this job started. Use Restart to begin a new partial file.":
        "Die Quelle hat sich seit dem Start geändert. „Von vorn beginnen“ legt eine neue Teildatei an.",
    "Connecting to PS5": "Verbinde mit der PS5",
    "Destination file already exists. Rename this job or explicitly enable replacement in a new job.":
        "Die Zieldatei gibt es schon. Den Auftrag umbenennen oder in einem neuen Auftrag das Ersetzen erlauben.",
    "Found a partial file without source history; restart this job.":
        "Eine Teildatei ohne bekannte Herkunft gefunden; bitte von vorn beginnen.",
    "Partial file is larger than the source or source length is unknown. Restart the job.":
        "Die Teildatei ist größer als die Quelle oder deren Größe unbekannt. Bitte von vorn beginnen.",
    "This link does not provide stable resume metadata. Restart, or download to your Mac and send the local file.":
        "Dieser Link lässt sich nicht sicher fortsetzen. Von vorn beginnen oder die Datei auf diesen Rechner laden und von dort senden.",
    "PS5 FTP refused upload/resume. Confirm write access and REST support, or restart the job.":
        "Der FTP-Server der PS5 lehnt Hochladen oder Fortsetzen ab. Schreibrechte und REST prüfen oder von vorn beginnen.",
    "Pre-buffering pipeline…": "Fülle den Puffer …",
    "Speed cap enabled": "Höchstgeschwindigkeit aktiv",
    "Waiting for source": "Warte auf die Quelle",
    "PS5 / local network": "PS5 / lokales Netzwerk",
    "Source byte count did not match. Incomplete file retained.":
        "Die Datenmenge der Quelle stimmte nicht. Die unvollständige Datei bleibt erhalten.",
    "Verifying PS5 file size": "Prüfe die Größe auf der PS5",
    "Local file changed while uploading. Partial retained; restart with a stable file.":
        "Die lokale Datei hat sich beim Hochladen geändert. Die Teildatei bleibt; bitte mit unveränderter Datei neu beginnen.",
    "Destination appeared during upload. Verified partial retained to avoid replacing it.":
        "Die Zieldatei ist während des Hochladens entstanden. Die geprüfte Teildatei bleibt, nichts wird ersetzt.",
    "Finalizing file": "Schließe die Datei ab",
    "Remote file size verified; not a cryptographic checksum.":
        "Größe auf der PS5 geprüft (keine kryptografische Prüfsumme).",
    "Direct Stream for PlayStation 5": "Direct Stream for PlayStation 5",
}

#: Texte mit Zahlen oder Namen: (regulaerer Ausdruck auf den ganzen Text, Ersatz). Reihenfolge zaehlt.
DEUTSCH_MUSTER: list[tuple[str, str]] = [
    (r"^(\d+) items?$", r"\1 Einträge"),
    (r"^(\d+) completed$", r"\1 fertig"),
    (r"^(\d+) selected$", r"\1 gewählt"),
    (r"^(\d+)m ago$", r"vor \1 min"),
    (r"^(\d+(?:\.\d+)?) ([KMGT]B) free$", r"\1 \2 frei"),
    (r"^(\d+) streams? · (\d+) MiB RAM$", r"\1 Ströme · \2 MiB Puffer"),
    (r"^(\d+) streams?$", r"\1 Ströme"),
    (r"^(\d+) transfers? added to queue$", r"\1 Übertragung(en) zur Warteschlange hinzugefügt"),
    (r"^(\d+) transfer added to queue$", r"\1 Übertragung zur Warteschlange hinzugefügt"),
    (r"^Found (\d+) packages in folder$", r"\1 Pakete im Ordner gefunden"),
    (r"^Remove (\d+) transfers from the queue\?$", r"\1 Übertragungen aus der Warteschlange entfernen?"),
    (r"^Copied path: (.+)$", r"Pfad kopiert: \1"),
    (r"^Dropped (\d+) file\(s\) into New Transfer$", r"\1 Datei(en) in „Neue Übertragung“ abgelegt"),
    (r"^Applied settings: (.+)$", r"Übernommen: \1"),
    (r"^Apply Recommended Settings: (.+)$", r"Empfohlene Einstellung übernehmen: \1"),
    (r"^Connection to the app was lost\. (.*)$", r"Die Verbindung zu Direct Stream ist weg. \1"),
    (r"^(\d+) streams × (\d+) MiB = (\d+) MiB min · (\d+) MiB RAM \((\d+) slots(?: cushion)?\)$",
     r"\1 Ströme × \2 MiB = mindestens \3 MiB · \4 MiB Puffer (\5 Plätze)"),
    (r"^⚠️ Buffer \((\d+) MiB\) < required (\d+) MiB \((\d+) streams × (\d+) MiB chunk\)$",
     r"⚠️ Puffer (\1 MiB) < nötig \2 MiB (\3 Ströme × \4 MiB je Stück)"),
    (r"^More actions for (.+)$", r"Weitere Aktionen für \1"),
    # Server
    (r"^(\w+) must be a whole number between (\d+) and (\d+)\.$", r"\1 muss eine ganze Zahl zwischen \2 und \3 sein."),
    (r"^A job named (.+) is already in the queue\. Use a different destination name\.$",
     r"„\1“ steht schon in der Warteschlange. Bitte einen anderen Zielnamen wählen."),
    (r"^Validating (\d+) queued links…$", r"Prüfe \1 Links der Warteschlange …"),
    (r"^Link verified · (.+)$", r"Link geprüft · \1"),
    (r"^Link check failed: (.+)$", r"Linkprüfung fehlgeschlagen: \1"),
    (r"^Source: parallel ranges available; resume available\.$",
     "Quelle: gleichzeitige Bereiche möglich; Fortsetzen möglich."),
    (r"^Source: (parallel ranges available|single stream only); resume (available|unavailable without stable source metadata)\.$",
     r"Quelle: \1; Fortsetzen: \2."),
    (r"^(.+): complete\. (.+)$", r"\1: fertig. \2"),
    (r"^(.+) verified on PS5$", r"\1 auf der PS5 geprüft"),
    (r"^Retry (\d+)/(\d+) in (\d+)s · (.+)$", r"Wiederholung \1/\2 in \3 s · \4"),
    (r"^Connected in (\d+) ms · destination folder found(.*)$", r"Verbunden in \1 ms · Zielordner gefunden\2"),
    (r"^Connected in (\d+) ms(.*)\. Destination will be created when uploading\.$",
     r"Verbunden in \1 ms\2. Der Zielordner entsteht beim Hochladen."),
    (r"^(\d+) entries in (.+)$", r"\1 Einträge in \2"),
    (r"^Resuming at (\d+) bytes$", r"Setze fort bei \1 Bytes"),
    (r"^Insufficient PS5 disk space: needs ([\d.]+) GB, but only ([\d.]+) GB is available\.$",
     r"Zu wenig Platz auf der PS5: nötig \1 GB, frei nur \2 GB."),
    (r"^PS5 size mismatch: expected (\d+) bytes, received (\d+)\. Partial retained; do not use it\.$",
     r"Größe auf der PS5 stimmt nicht: erwartet \1 Bytes, erhalten \2. Die Teildatei bleibt – bitte nicht benutzen."),
    (r"^Upload size verified, but rename failed\. Your complete file is (.+); rename it on PS5\. No file was deleted\.$",
     r"Größe geprüft, aber das Umbenennen scheiterte. Die vollständige Datei heißt \1 – bitte auf der PS5 umbenennen. Nichts wurde gelöscht."),
    (r"^Temporary download server error: HTTP (\d+)$", r"Vorübergehender Fehler des Download-Servers: HTTP \1"),
    (r"^Download server returned HTTP (\d+)\. Check the direct link or get a fresh one\.$",
     r"Der Download-Server antwortet mit HTTP \1. Link prüfen oder einen neuen holen."),
    (r"^Unexpected HTTP (\d+)\.$", r"Unerwartete Antwort: HTTP \1."),
    (r"^Range request returned HTTP (\d+); source may have changed\. Refresh the link or use one stream\.$",
     r"Bereichsabfrage lieferte HTTP \1; die Quelle hat sich vielleicht geändert. Link erneuern oder nur einen Strom nutzen."),
    (r"^HTTP range failed after 3 attempts: (.+)$", r"Bereichsabfrage nach 3 Versuchen gescheitert: \1"),
    (r"^Timed out waiting for the download server\. (.+)$",
     "Zeitüberschreitung beim Download-Server. Er startet vielleicht langsam, begrenzt oder blockiert wiederholte Anfragen."),
    (r"^Timed out waiting for the PS5 or source\. (.+)$",
     "Zeitüberschreitung bei PS5 oder Quelle. Sie startet vielleicht langsam, begrenzt oder blockiert wiederholte Anfragen."),
    (r"^SSL certificate check failed on the download link\..*$",
     "Die Zertifikatsprüfung des Download-Links ist gescheitert. Bitte Link und Systemzertifikate prüfen."),
    (r"^(\w+): (.+)\. Check the source link, network, and PS5 FTP server\.$",
     r"\1: \2. Quelle, Netzwerk und FTP-Server der PS5 prüfen."),
    (r"^This link does not support byte ranges; only a single stream is possible: ([\d.]+) MB/s\.$",
     r"Dieser Link kann keine Bereiche; möglich ist nur ein Strom: \1 MB/s."),
]

#: Wortgruppen, die in vielen zusammengesetzten Texten stehen (Messergebnisse, Vorgaben). Nur angewandt, wenn weder
#: ein ganzer Text noch ein Muster passt.
DEUTSCH_TEILE: list[tuple[str, str]] = [
    ("Low-Bandwidth / Wi-Fi Tier", "Langsame Leitung / WLAN"),
    ("Standard Entry Broadband", "Einfacher Breitbandanschluss"),
    ("Stable Mid-Bandwidth", "Mittlere Leitung"),
    ("Balanced Default", "Ausgewogene Vorgabe"),
    ("High-Speed Fiber", "Schnelle Glasfaser"),
    ("Fast Turbo", "Turbo"),
    ("Ultra-Wide Pipeline", "Breite Leitung"),
    ("Max Saturation", "Maximum"),
    ("Tier 1: Conservative / Wi-Fi", "Stufe 1: Vorsichtig / WLAN"),
    ("Tier 2: Balanced Standard", "Stufe 2: Ausgewogen"),
    ("Tier 3: Gigabit Turbo", "Stufe 3: Gigabit-Turbo"),
    ("🏆 Optimal config:", "🏆 Beste Einstellung:"),
    ("Each tier tested against actual direct download chunks. Bytes discarded from RAM.",
     "Jede Stufe mit echten Stücken des Downloads gemessen. Die Daten wurden verworfen."),
    ("Bytes discarded from RAM; PS5 was not contacted.", "Die Daten wurden verworfen; die PS5 war nicht beteiligt."),
    ("first data after", "erste Daten nach"),
    ("first data:", "erste Daten:"),
    ("whole test incl. startup", "ganzer Test samt Anlauf"),
    ("Steady", "Dauerhaft"),
    ("single stream (server does not support ranges, or streams = 1)",
     "ein Strom (der Server kann keine Bereiche, oder Ströme = 1)"),
    ("MiB ranges", "MiB-Bereiche"),
    ("GB free on PS5", "GB frei auf der PS5"),
    (" streams × ", " Ströme × "),
    (" streams ", " Ströme "),
    ("MiB chunk", "MiB je Stück"),
    ("MiB RAM", "MiB Puffer"),
    ("Working…", "Arbeite …"),
]


def _normal(text: str) -> str:
    return " ".join(str(text).split())


def uebersetzen(text: str, sprache: str) -> str:
    """Ein Text so, wie ihn das Skript im Browser ersetzen wuerde - fuer Pruefungen in Python.

    Gleiche Regeln wie :func:`skript`: erst der ganze Text, dann die Muster, dann die Wortgruppen. Unbekanntes
    bleibt, wie es ist.
    """
    kern = _normal(text)
    if sprache != "de":
        return NEUTRAL.get(kern, text)
    if kern in DEUTSCH:
        return DEUTSCH[kern]
    for muster, ersatz in DEUTSCH_MUSTER:
        if re.match(muster, kern):
            return re.sub(muster, ersatz, kern)
    neu = kern
    for alt, ersatz in DEUTSCH_TEILE:
        neu = neu.replace(alt, ersatz)
    return neu if neu != kern else text


def skript(sprache: str) -> str:
    """Das Skript, das die Oberflaeche im Browser uebersetzt (deutsch) oder neutral haelt (sonst).

    Es laeuft vor ``app.js`` (im ``<head>`` eingefuegt, :func:`seite_einrichten`), ersetzt Textknoten und die
    Attribute ``placeholder``, ``title``, ``aria-label`` und haelt mit einem ``MutationObserver`` alles nach, was
    spaeter erscheint. ``confirm`` und ``alert`` werden umhuellt, damit auch Rueckfragen uebersetzt sind.
    Eingabefelder (``value``) bleiben unberuehrt - das sind Daten des Anwenders.
    """
    if sprache == "de":
        # Python-Rueckverweise \1 -> JavaScript $1
        ganz, teile = DEUTSCH, DEUTSCH_TEILE
        muster = [(m, re.sub(r"\\(\d)", r"$\1", r)) for m, r in DEUTSCH_MUSTER]
    else:
        ganz, muster, teile = NEUTRAL, [], []
    daten = json.dumps({"ganz": ganz, "muster": [[m, r] for m, r in muster], "teile": teile},
                       ensure_ascii=False).replace("</", "<\\/")
    return """(function () {
  "use strict";
  var D = %s;
  var MUSTER = D.muster.map(function (p) { return [new RegExp(p[0]), p[1]]; });
  function normal(s) { return s.replace(/\\s+/g, " ").trim(); }
  function tr(s) {
    if (!s || !/[A-Za-z]/.test(s)) { return null; }
    var k = normal(s);
    if (Object.prototype.hasOwnProperty.call(D.ganz, k)) { return D.ganz[k]; }
    for (var i = 0; i < MUSTER.length; i++) {
      if (MUSTER[i][0].test(k)) { return k.replace(MUSTER[i][0], MUSTER[i][1]); }
    }
    var neu = k;
    for (var j = 0; j < D.teile.length; j++) { neu = neu.split(D.teile[j][0]).join(D.teile[j][1]); }
    return neu !== k ? neu : null;
  }
  function textknoten(n) {
    var alt = n.nodeValue, neu = tr(alt);
    if (neu !== null && neu !== normal(alt)) {
      var vor = alt.match(/^\\s*/)[0], nach = alt.match(/\\s*$/)[0];
      n.nodeValue = vor + neu + nach;
    }
  }
  var ATTR = ["placeholder", "title", "aria-label"];
  function element(el) {
    if (el.nodeType !== 1) { return; }
    var tag = el.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "TEXTAREA") { return; }
    for (var i = 0; i < ATTR.length; i++) {
      var a = el.getAttribute(ATTR[i]);
      if (a) { var n = tr(a); if (n !== null && n !== a) { el.setAttribute(ATTR[i], n); } }
    }
  }
  function baum(wurzel) {
    if (wurzel.nodeType === 3) { textknoten(wurzel); return; }
    if (wurzel.nodeType !== 1) { return; }
    element(wurzel);
    var gang = document.createTreeWalker(wurzel, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = gang.nextNode())) {
      if (n.nodeType === 3) {
        var p = n.parentNode && n.parentNode.tagName;
        if (p !== "SCRIPT" && p !== "STYLE" && p !== "TEXTAREA") { textknoten(n); }
      } else { element(n); }
    }
  }
  var beob = new MutationObserver(function (liste) {
    beob.disconnect();
    liste.forEach(function (m) {
      if (m.type === "characterData") { textknoten(m.target); }
      else if (m.type === "attributes") { element(m.target); }
      else { m.addedNodes.forEach(baum); }
    });
    beob.observe(document.documentElement, OPTIONEN);
  });
  var OPTIONEN = { childList: true, subtree: true, characterData: true, attributes: true,
                   attributeFilter: ATTR };
  var c = window.confirm, a = window.alert;
  window.confirm = function (s) { var n = tr(String(s)); return c.call(window, n === null ? s : n); };
  window.alert = function (s) { var n = tr(String(s)); return a.call(window, n === null ? s : n); };
  function los() { baum(document.documentElement); beob.observe(document.documentElement, OPTIONEN); }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", los); } else { los(); }
  document.title = (tr(document.title) || document.title);
})();
""" % daten


def seite_einrichten(seite: str, sprache: str) -> str:
    """index.html mit dem Uebersetzungsskript (vor ``app.js``) und der Sprache im ``<html>``."""
    seite = seite.replace('<html lang="en">', '<html lang="%s">' % ("de" if sprache == "de" else "en"), 1)
    return seite.replace("<head>", '<head>\n  <script src="%s"></script>' % SKRIPT_PFAD, 1)
