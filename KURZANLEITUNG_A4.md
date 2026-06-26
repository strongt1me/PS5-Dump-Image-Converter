# PS5 Dump & Image Converter - A4 Kurzuebersicht

## Schnellstart

1. Programm starten.
2. Aufgabe auswaehlen.
3. Quelle waehlen.
4. Zielordner waehlen.
5. Start klicken.
6. Auf Fertig-Meldung warten.

## Aufgaben (1-8)

1. Game Dump Ordner -> ffpfsc
2. ffpfsc -> exFAT
3. exFAT -> ffpfsc
4. ffpfsc -> Game Dump Ordner
5. exFAT -> Game Dump Ordner
6. ffpkg -> ffpfsc
7. fakelib Manager
8. Dump Validator

## Ressourcen (19-21)

Im Ressourcen-Fenster:

- [19] OSFMount automatisch installieren
- [20] Dokan2 automatisch installieren
- [21] FileZilla automatisch installieren

Hinweis:

- Bereits installierte Tools werden nicht neu installiert.
- Installation laeuft im Hintergrund.

## Haeufige Probleme

1. Installer startet nicht:
   - Programm als Administrator starten.
   - Internetverbindung pruefen.
2. UAC-Fenster erscheint:
   - Mit Ja bestaetigen.
3. Antivirus blockiert:
   - Ausnahme fuer Programm/Installer setzen.
4. Modusfehler:
   - Dateiendung pruefen (.ffpfsc/.exfat/.ffpkg).

## Vor jedem Lauf kurz pruefen

1. Genug Speicherplatz vorhanden.
2. Richtige Aufgabe ausgewaehlt.
3. Quelle und Ziel korrekt gesetzt.
4. Bei fehlenden Tools zuerst Ressourcen 19-21 nutzen.

## Release-Kurzcheck

1. test_build_ready.py -> 7/7
2. test_all_quality.py -> 7/7
3. EXE Starttest
4. Aufgaben-Smoke-Test inkl. 19-21
