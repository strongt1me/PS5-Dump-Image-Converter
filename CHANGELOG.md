# Changelog

Alle nennenswerten Aenderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [Aktueller Stand] - 2026-07-07

### Aufgabe 7 / .ffpkg / Admin-Runner
- Aufgabe 7 akzeptiert jetzt auch `.ffpkg` als Quelle in Auswahl, Validierung und Workflow.
- `.ffpkg`-Quellen werden fuer fakelib-/Root-Aenderungen ueber den vorhandenen UFS2Tool-/Dokan-Pfad extrahiert und danach bewusst als `.ffpfsc` neu verpackt, weil kein `.ffpkg`-Schreibpfad vorhanden ist.
- Die GUI weist fuer Aufgabe 7 sichtbar darauf hin, dass `.ffpkg`-Eingaben als `.ffpfsc` ausgegeben werden.
- Der E2E-Runner deckt jetzt zusaetzlich `A7_ffpkg_fakelib_manager` ab und verifiziert je nach Ausgabeformat sowohl `.exfat`- als auch `.ffpfsc`-Artefakte korrekt.
- `Run_Tasks_1_8_Admin.ps1` unterstuetzt jetzt gezielte erhoehte Einzellaeufe ueber `-Task`; fuer Aufgabe 7 mit `.ffpkg` ist zudem ein Komfortstarter vorhanden.
- Frische Admin-Verifikation bestaetigt `A7_fakelib_manager`, `A7_files_add`, `A7_files_remove` und `A7_ffpkg_fakelib_manager` jeweils als PASS.

### Aufgabe 1 / Fortschritt / Resume
- Frischen Neustart nach abgebrochenem `mkpfs pack file` gehaertet: die App wartet vor dem Neuversuch auf auslaufende Hintergrundarbeit und entfernt verwaiste Zielartefakte.
- Kompressionsfortschritt bleibt im korrekten Schritt-2-Bereich statt in spaetere Phasen zu rutschen.
- Pulse-Creep waehrend der MkPFS-Kompression unterdrueckt, damit echte Engine-Signale die GUI fuehren.
- Wiederholte `compress`-Logzeilen reduziert und Phase 4/4 sichtbar gehalten.

### Aufgabe 2 / Vorschau / Fortschritt
- Vorschau und Infobox fuer `.ffpfsc` aus Aufgabe 1 und 3 nutzen jetzt zuerst benachbarte Task-/E2E-Reports als Fast-Path statt langsames Container-Parsen.
- Schrittgeometrie fuer `.ffpfsc -> .exfat` korrigiert: frueher outer-unpack startet nicht mehr im 0-95%-Bereich.
- Fruehe Branch-Erkennung aus Reports verbessert die Fortschrittsanzeige bereits vor Abschluss des ersten Unpack-Schritts fuer Aufgabe-1- und Aufgabe-3-Artefakte.

### Aufgaben 3 bis 8 / Validierung
- Aufgabe 3 und Aufgabe 6 bleiben direkte Ein-Schritt-Pfade mit konsistentem 0-98%-Mapping.
- Aufgabe 4 gegen Schrittueberlaeufe gehaertet: Abschlussaeste verwenden wieder den letzten gueltigen Schritt, und die generische Schrittlogik klemmt Ausreisser defensiv auf die definierte Schrittzahl.
- Erhoehter Gesamtlauf bestaetigt A1-A6 und A8 als PASS; A7 bleibt erwartungsgemaess `MANUAL_REQUIRED`.
- Nicht-erhoehte Einzeltests von Aufgabe 5 koennen weiterhin an OSFMount/UAC (`WinError 740`) scheitern; das ist als Umgebungsbedingung dokumentiert, nicht als Aufgabenlogikfehler.

### Referenz-Commits
- 790d215 fix: harden task1 restart after aborted pack
- 17824cb fix: keep task1 compress progress in step2 range
- 325be92 fix: stop pulse creep during task1 compress
- 568dad2 fix: reduce task1 compress log spam and show phase4
- 02ff061 fix: speed up task2 preview from task reports
- 94dab7d fix: correct task2 progress step ranges
- 6c533c6 fix: hint task2 progress geometry from reports
- 1acf6f8 fix: clamp task4 progress to valid steps

## [Aktueller Stand] - 2026-07-06

### Build
- MIT-only Flow im Build erzwungen (kein EV/PFX Pflichtpfad im Standardablauf).
- Signatur-Parameter werden im MIT-only Modus aktiv blockiert.
- Signatur-Vorpruefung und MIT-Registry-Registrierung in den Build-Flow integriert.

### Runtime
- MIT-Lizenz wird beim Start der Anwendung in HKCU registriert (vor Hauptprogramm-Start).
- Sichtbare Startmeldung im GUI-Log fuer Erfolg/Warnung der MIT-Registry-Registrierung.

### Signierung
- SignTool-Suche robuster gemacht (ProgramFiles/ProgramFilesX86/PATH Fallback).
- Sichere Behandlung von PFX-Passwoertern verbessert.

### Referenz-Commits
- 7444110 build: enforce MIT-only flow and runtime license registration
- 3ff9c2b fix: correct PowerShell path escaping in Sign_EXE.ps1 for (x86) directories

## [v1.7.80] - 2026-07-06

### Aufgabe 1 / MkPFS / Runtime
- Resume fuer Aufgabe 1 verbessert: bei vorhandenem Zwischen-Image wird der lange Phase-1-Scan uebersprungen.
- Doppelstart der App im EXE-/frozen-Modus behoben: `pip`-Aufrufe verwenden jetzt einen echten Python-/Py-Launcher statt `sys.executable -m pip`.
- `zlib_ng` ist nicht mehr harte Pflichtabhaengigkeit; bei Python-3.14-/Wheel-Inkompatibilitaet faellt MkPFS automatisch auf stdlib-`zlib` zurueck.
- Namenskollision in `MkPFS-0.0.9/mkpfs/logging.py` mit stdlib-`logging` behoben.

### GUI / UX / Stabilitaet
- Release-Test-Gate vor Task-Start eingefuehrt: Aufgaben mit Zielartefakt starten nur noch bei aktuellem PASS-Status aus den Release-Tests.
- Sichtbare Release-Gate-Anzeige in der GUI ergaenzt (PASS/BLOCKIERT/N/A inkl. Suite/Alter/Legende).
- GUI-Responsiveness bei langem MkPFS-Pack verbessert: Engine-Queue pro Tick begrenzt, Log-Ausgabe gebuendelt und `0% compress`-Spam gedrosselt.
- Hintergrund-Installer zeigen waehrend laufender Aufgaben keine stoerenden modalen Popups mehr.

### Tests / Verifizierung
- Release-Test-Skripte schreiben jetzt einen maschinenlesbaren Statusreport fuer das Runtime-Gate.
- Full Suite, Quick Smoke und Hotfix Smoke wurden mit dem neuen Workflow verifiziert.

### Weitere Aenderungen
- Aufgabe 7 erweitert: automatische AMPR-Index-Generierung (`ampr_emu.index`) nach fakelib-/Root-Aenderungen.
- AMPR-Root-Erkennung verbessert: direkter `fakelib`-Pfad wird automatisch auf den Parent normalisiert.
- E2E-/AMPR-Lokaldateien in `.gitignore` aufgenommen und Repo-Hygiene verbessert.

## [v1.7.78] - 2026-07-06

- Entfernt die ungenutzte Legacy-UFS2Tool-/Dokan-Einbettung aus ps5-exfat-builder v3.6.4.
- Aufgabe 6 nutzt nur noch den direkten aktuellen `.ffpkg -> .ffpfsc`-Pfad ohne alte Binär-Bundles.

## [v1.7.77] - 2026-07-06

- Entfernt den veralteten EV-/PFX-/Code-Signing-Releasepfad aus den Build-Skripten.
- MIT-Lizenz wird nur noch beim EXE-Start in HKCU registriert, nicht mehr waehrend des Builds.
- Build-Starter arbeitet ohne Get-/Set-ExecutionPolicy-Abhaengigkeit und laeuft dadurch robuster in reduzierten PowerShell-Umgebungen.
- Entfernt die ungenutzte UFS2Tool-/Dokan-Altintegration aus ps5-exfat-builder v3.6.4; Aufgabe 6 nutzt nur noch den aktuellen direkten .ffpkg -> .ffpfsc-Pfad.

## [v1.7.76] - 2026-07-06

### Security
- Signier-Passwort im Build-Skript auf SecureString umgestellt.

### Build
- Ungueltige PyInstaller hidden imports entfernt.

### Tests
- Wording im Quick-Smoke Build-Readiness Test korrigiert.

### Repo Hygiene
- PS5 ELF-Dateien (helloworld/*.elf) in .gitignore aufgenommen.

### Referenz-Commits
- f8fa242 chore: add helloworld/*.elf to .gitignore (PS5 binaries not needed in repo)
- 4e08a93 security: use SecureString for signing password in build script
- 450d778 build: remove invalid pyinstaller hidden imports
- d16a9a1 test: fix quick smoke build-readiness wording

## [Projektupdate] - 2026-07-06

### Features
- Build-, Signier- und E2E-Updates konsolidiert und persistiert.

### Referenz-Commit
- 5f068d1 feat: persist build, signing and e2e updates

## [Wartung] - 2026-07-06

### Repo Hygiene
- Diverses-Inhalte aus Tracking entfernt und Ordner ignoriert.

### Referenz-Commit
- 1450ef6 chore(git): remove Diverses content from tracking and ignore folder

## [Projekthygiene] - 2026-06-26

### Repo Hygiene
- Python-Cache-Artefakte entfernt und Ignorierregeln erweitert.
- .gitignore fuer venv, IDE und Build-Artefakte ausgebaut.

### Referenz-Commits
- 27db715 Erweitere .gitignore fuer venv, IDE und Build-Artefakte
- 64ae095 Ignore und entferne Python-Cache-Artefakte

## [Projektstand] - 2026-06-26

### Snapshot
- Projektstand aktualisiert (ohne _live_task6_output).

### Referenz-Commit
- 1a286e9 Projektstand aktualisiert (ohne _live_task6_output)

## [Initiale Version] - 2026-06-25

### Initialisierung
- Erstimport des Projekts.
- Erste Dateiuploads und Grundstruktur angelegt.

### Referenz-Commits
- dd8e6c3 Add files via upload
- 6140c6f Initial commit

## Vollstaendige Commit-Chronik (alt -> neu)

- 6140c6f | 2026-06-25 | Initial commit
- dd8e6c3 | 2026-06-25 | Add files via upload
- 1a286e9 | 2026-06-26 | Projektstand aktualisiert (ohne _live_task6_output)
- 64ae095 | 2026-06-26 | Ignore und entferne Python-Cache-Artefakte
- 27db715 | 2026-06-26 | Erweitere .gitignore fuer venv, IDE und Build-Artefakte
- 1450ef6 | 2026-07-06 | chore(git): remove Diverses content from tracking and ignore folder
- 5f068d1 | 2026-07-06 | feat: persist build, signing and e2e updates
- d16a9a1 | 2026-07-06 | test: fix quick smoke build-readiness wording
- 450d778 | 2026-07-06 | build: remove invalid pyinstaller hidden imports
- 4e08a93 | 2026-07-06 | security: use SecureString for signing password in build script
- f8fa242 | 2026-07-06 | chore: add helloworld/*.elf to .gitignore (PS5 binaries not needed in repo)
- 3ff9c2b | 2026-07-06 | fix: correct PowerShell path escaping in Sign_EXE.ps1 for (x86) directories
- 7444110 | 2026-07-06 | build: enforce MIT-only flow and runtime license registration
