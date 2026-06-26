# Kurz-Anleitung (1 Seite)

## Quick Start

1. Programm starten:

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

2. Modus auswaehlen (Aufgabe 1-8) und Quelle/Ziel setzen.
3. Start klicken und Fortschritt abwarten.
4. Ergebnis im Zielordner pruefen.

## Wichtigste Modi

1. Game Dump Ordner -> ffpfsc
2. ffpfsc -> exFAT
3. exFAT -> ffpfsc
4. ffpfsc -> Game Dump Ordner
5. exFAT -> Game Dump Ordner
6. ffpkg -> ffpfsc
7. fakelib Manager
8. Dump Validator

## Neue Komfort-Funktionen (Ressourcen 19-21)

Im Ressourcen-Fenster:

- [19] OSFMount automatisch installieren
- [20] Dokan2 automatisch installieren
- [21] FileZilla automatisch installieren

Hinweise:

- Vor der Installation wird geprueft, ob das Tool bereits vorhanden ist.
- Bereits installierte Tools werden nicht erneut installiert.
- Die Installation laeuft im Hintergrund.

## Haeufige Fehler und schnelle Loesung

1. OSFMount/Dokan2 fehlt:
   - Ressourcen-Fenster oeffnen und [19]/[20] nutzen.
2. FileZilla nicht gefunden:
   - [21] nutzen oder filezilla.exe manuell auswaehlen.
3. UAC/Antivirus blockiert Setup:
   - Als Administrator starten und Sicherheitsabfrage bestaetigen.
4. Build-Fehler:
   - Abhaengigkeiten neu installieren und Build erneut starten.

## Build in 1 Befehl

```powershell
powershell -ExecutionPolicy Bypass -File .\Build_EXE.ps1
```

## Release-Check (kurz)

1. test_build_ready.py -> 7/7
2. test_all_quality.py -> 7/7
3. EXE-Starttest auf Zielsystem
4. Aufgaben-Smoke-Test (inkl. 19-21)
