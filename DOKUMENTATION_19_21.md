# Dokumentation 19-21 (Automatische Hintergrund-Installation)

## Uebersicht

Im Ressourcen-Fenster wurden drei Aktionen implementiert:

- [19] OSFMount installieren
- [20] Dokan2 installieren
- [21] FileZilla installieren

Ziel: Download und Installation automatisch im Hintergrund ausfuehren.

## Bedienung

1. Hauptfenster starten
2. Ressourcen oeffnen
3. Zur Sektion 19-21 scrollen
4. Gewuenschte Aktion anklicken

## Ablauf pro Aktion

1. Vorpruefung:
   - Tool bereits installiert?
   - Falls ja: Installation wird uebersprungen und als erfolgreich gemeldet.
2. Wenn nicht installiert:
   - Download starten
   - Stille Installation starten
   - Nachpruefung (Tool jetzt vorhanden?)
3. Ergebnis:
   - Erfolgsmeldung oder Fehlermeldung

## UI-Verhalten

- GUI bleibt waehrend Installation bedienbar.
- Es kann immer nur eine Installation gleichzeitig laufen.
- Bei parallelem Startversuch erscheint ein Hinweisdialog.
- Status-/Dialogtexte enthalten ein Praefix [19], [20], [21].

## Fehlerszenarien

Moegliche Ursachen bei Fehlschlag:

- Keine Internetverbindung
- Download-URL temporaer nicht erreichbar
- UAC-Bestaetigung abgelehnt
- AV/Endpoint Security blockiert Setup
- Keine ausreichenden Rechte

## Testhinweise

Sicherer Test (ohne echte Installation):

- Mock-/Simulationstest ueber interne Callbacks (Entwicklertest)

Echter Test:

1. Tool deinstallieren oder auf frischem System testen
2. Aktion [19], [20], [21] ausfuehren
3. Nach Abschluss Vorhandensein des Tools pruefen

## Technische Notizen

- Thread-sichere UI-Updates wurden gehaertet (RuntimeError-Abfang bei Tk-Shutdown-Race).
- Vor Download/Setup wird immer verify_func geprueft, um Neuinstallationen zu vermeiden.
