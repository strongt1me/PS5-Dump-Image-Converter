# Release-Dokumentation

## Status

Stand: 2026-06-26

Release-Readiness-Checks:

- test_build_ready.py: 7/7 bestanden
- test_all_quality.py: 7/7 bestanden
- py_compile Hauptdatei: erfolgreich

Aktuelle Einschaetzung:

- Das Projekt ist build- und release-bereit.

## Build

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\Build_EXE.ps1
```

Erwartetes Ergebnis:

- EXE im Verzeichnis dist/
- Dateiname laut Version in README/Spec

## Optionales Signing

```powershell
.\Sign_EXE.ps1 -ExePath "dist\PS5_Dump_Image_Converter_v1.7.76.exe" -PfxPath "C:\Pfad\zertifikat.pfx" -PfxPassword "<passwort>"
```

## Release-Checkliste

1. Build erfolgreich (keine Fehler im Build-Log)
2. EXE-Starttest auf Zielsystem
3. Smoke-Test Aufgaben 1-8
4. Ressourcen-Fenster pruefen, inkl. 19-21
5. Changelog aktualisiert
6. Release-Artefakte archivieren

## Bekannte Rest-Risiken

- Externe Installer (OSFMount, Dokan2, FileZilla) haengen von Internet/UAC/AV-Richtlinien ab.
- Auf restriktiven Systemen koennen stille Installer geblockt werden.
- Mount-/Treiberfunktionen koennen Adminrechte benoetigen.

## Empfehlung vor finalem Public Release

- Ein finaler End-to-End GUI-Lauf auf einem frischen Windows-System
- Optional: Signierung und erneuter AV/SmartScreen-Schnelltest
