# Release Test Checkliste

Ziel:
- Vollständiger End-to-End Test für Aufgabe 1 bis 8
- GUI- und Stabilitätsprüfung
- Klare Freigabeentscheidung vor Build/Release

Hinweise zur Nutzung:
- Pro Schritt Ergebnis eintragen: PASS, FAIL, BLOCKED
- Dauer in Minuten eintragen
- Relevante Log-Zeile oder Kurznotiz dokumentieren

## 1) Testdaten vorbereiten

| ID | Schritt | Erwartung | Ergebnis | Dauer (min) | Log-Hinweis |
|---|---|---|---|---|---|
| DATA-01 | DumpA mit eboot.bin und sce_sys/param.json vorhanden | Vollständiger Referenz-Dump |  |  |  |
| DATA-02 | DumpBroken ohne eboot.bin vorhanden | Unvollständiger Dump für Validator-Test |  |  |  |
| DATA-03 | Zielordner für Ausgaben angelegt | Saubere Trennung je Aufgabe |  |  |  |

## 2) Aufgaben 1 bis 8

| ID | Aufgabe | Eingabe | Erwartung | Ergebnis | Dauer (min) | Log-Hinweis |
|---|---|---|---|---|---|---|
| A1 | 1. Game Dump Ordner zu ffpfsc | DumpA | ffpfsc Datei erstellt, kein Abbruch |  |  |  |
| A2 | 2. ffpfsc zu exFAT | Ausgabe aus A1 | exfat Datei erstellt, kein Abbruch |  |  |  |
| A3 | 3. exFAT zu ffpfsc | Ausgabe aus A2 | neue ffpfsc Datei erstellt |  |  |  |
| A4 | 4. ffpfsc zu Game Dump Ordner | Ausgabe aus A1 oder A3 | Ordner mit eboot.bin und sce_sys/param.json |  |  |  |
| A5 | 5. exFAT zu Game Dump Ordner | Ausgabe aus A2 | Ordnerinhalt plausibel und vollständig |  |  |  |
| A6 | 6. ffpkg zu ffpfsc | Beispiel ffpkg | ffpfsc Ausgabe ohne Fehler |  |  |  |
| A7 | 7. fakelib Manager | DumpA oder ffpfsc/exfat | Suchen/Löschen/Hinzufügen funktioniert |  |  |  |
| A8-OK | 8. Dump Validator (vollständig) | DumpA | Status OK |  |  |  |
| A8-FAIL | 8. Dump Validator (unvollständig) | DumpBroken | Fehlerdiagnose mit fehlenden kritischen Dateien |  |  |  |

## 3) Roundtrip-Konsistenz

| ID | Schritt | Erwartung | Ergebnis | Dauer (min) | Log-Hinweis |
|---|---|---|---|---|---|
| RT-01 | DumpA -> A1 -> A2 -> A3 | Pipeline ohne Crash |  |  |  |
| RT-02 | A3 -> A4 | Rückgewonnener Ordner ist lauffähig/valide Struktur |  |  |  |
| RT-03 | A2 -> A5 | Ordnerstruktur konsistent mit Erwartung |  |  |  |

## 4) GUI und UX

| ID | Check | Erwartung | Ergebnis | Dauer (min) | Log-Hinweis |
|---|---|---|---|---|---|
| GUI-01 | App-Start | Fenster startet ohne Ausnahme | PASS | 1 | GUI_INIT_OK True (programmatischer Smoke-Test) |
| GUI-02 | Moduswechsel 1 bis 8 | Quelle/Ziel-Felder korrekt sichtbar/unsichtbar |  |  |  |
| GUI-03 | Fortschrittsbalken | Monoton steigend, keine Sprünge rückwärts |  |  |  |
| GUI-04 | ETA-Anzeige | Nur bei ausreichend Laufzeit/Fortschritt sichtbar |  |  |  |
| GUI-05 | Laufender Task | Start/Stop Buttons korrekt deaktiviert/aktiviert |  |  |  |
| GUI-06 | Log-Fenster | Lesbar, keine kaputten Zeilen, klare Fehlermeldungen |  |  |  |

## 5) Regression und Build

| ID | Check | Erwartung | Ergebnis | Dauer (min) | Log-Hinweis |
|---|---|---|---|---|---|
| REG-01 | Syntax-Check | py_compile ohne Fehler | PASS | 1 | Exit Code 0 |
| REG-02 | Build-Readiness | Alle Tests grün | PASS | 2 | test_build_ready.py: 7/7 bestanden |
| REG-03 | Optional Full-Quality | Keine neuen kritischen Findings | FAIL | 3 | test_all_quality.py: 6/7, nur CodeQuality-Hinweis (doppelte Leerzeilen) |

## 6) Freigabeentscheidung

| Punkt | Eintrag |
|---|---|
| Datum | 2026-06-26 |
| Tester |  |
| Version | v1.7.76 |
| Gesamtstatus | BLOCKED (E2E Aufgabe 1-8 noch offen) |
| Kritische Blocker |  |
| Go für Build/Release | JA / NEIN |
| Bemerkungen | Vorabchecks grün bis auf optionalen Style-Hinweis in Full-Quality. |

## 7) Schnelle Kommandos (optional)

Syntax-Check:
C:/Users/JBuserc0re/AppData/Local/Python/pythoncore-3.14-64/python.exe -m py_compile PS5ImageConverter_Pro_FINAL_revised.py

Build-Readiness:
C:/Users/JBuserc0re/AppData/Local/Python/pythoncore-3.14-64/python.exe test_build_ready.py

Quality-Suite:
C:/Users/JBuserc0re/AppData/Local/Python/pythoncore-3.14-64/python.exe test_all_quality.py

## 8) E2E-Durchlaufblock (Live)

Ziel:
- Ein kompletter Praxisdurchlauf in sinnvoller Reihenfolge
- Schnelles Eintragen während des Tests

Reihenfolge:
1. A1 mit DumpA
2. A2 mit A1-Ausgabe
3. A3 mit A2-Ausgabe
4. A4 mit A3-Ausgabe
5. A5 mit A2-Ausgabe
6. A7 mit A1- oder A2-Ausgabe
7. A8-OK mit DumpA
8. A8-FAIL mit DumpBroken
9. Optional A6 mit ffpkg-Testdatei

| Seq | Schritt | Input | Output | Ergebnis | Dauer (min) | Notiz/Log |
|---|---|---|---|---|---|---|
| 1 | A1 | DumpA Ordner | game_a1.ffpfsc |  |  |  |
| 2 | A2 | game_a1.ffpfsc | game_a2.exfat |  |  |  |
| 3 | A3 | game_a2.exfat | game_a3.ffpfsc |  |  |  |
| 4 | A4 | game_a3.ffpfsc | folder_a4 |  |  |  |
| 5 | A5 | game_a2.exfat | folder_a5 |  |  |  |
| 6 | A7 | game_a1.ffpfsc oder game_a2.exfat | fakelib geändert |  |  |  |
| 7 | A8-OK | DumpA | Validator OK |  |  |  |
| 8 | A8-FAIL | DumpBroken | Diagnose fehlende kritische Dateien |  |  |  |
| 9 | A6 (optional) | sample.ffpkg | game_a6.ffpfsc |  |  |  |

Abschlusskriterium E2E:
- PASS, wenn Seq 1 bis 8 erfolgreich sind und keine kritischen GUI-Fehler auftreten.
- BLOCKED, wenn Input-Dateien fehlen.
- FAIL, wenn ein Schritt reproduzierbar abstürzt oder falsche Ausgabe erzeugt.

## 9) Quick Smoke (15 Minuten)

Ziel:
- Sehr schneller Sicherheitscheck vor Build/Upload
- Fokus auf Startfähigkeit, Kernpfad und Validator

Zeitbudget:
- Gesamt: 15 Minuten

| T+ | Check | Erwartung | Ergebnis | Notiz/Log |
|---|---|---|---|---|
| 00:00-02:00 | App starten und Moduswechsel (1, 2, 8) | Keine UI-Fehler, Felder schalten korrekt |  |  |
| 02:00-05:00 | A1 mit kleinem DumpA | ffpfsc wird erzeugt |  |  |
| 05:00-08:00 | A2 mit A1-Ausgabe | exfat wird erzeugt |  |  |
| 08:00-10:00 | A8-OK mit DumpA | Validator meldet OK |  |  |
| 10:00-12:00 | A8-FAIL mit DumpBroken | Fehlende kritische Dateien werden klar genannt |  |  |
| 12:00-13:00 | Syntax-Check | py_compile ohne Fehler |  |  |
| 13:00-15:00 | Build-Readiness | test_build_ready 7/7 grün |  |  |

Quick-Smoke-Go:
- JA, wenn alle Zeilen PASS sind.
- NEIN, sobald ein reproduzierbarer Absturz oder ein falsches Validator-Ergebnis auftritt.

## 10) Notfall Smoke (5 Minuten, Hotfix)

Ziel:
- Schnellstmögliche Mindestabsicherung bei zeitkritischem Hotfix

Regel:
- Nur nutzen, wenn ein vollständiger Quick-Smoke (15 Min) zeitlich nicht möglich ist.

| T+ | Check | Erwartung | Ergebnis | Notiz/Log |
|---|---|---|---|---|
| 00:00-01:00 | App-Start | Fenster öffnet ohne Ausnahme |  |  |
| 01:00-02:00 | Moduswechsel 1 und 8 | UI reagiert korrekt, keine Fehlerdialoge |  |  |
| 02:00-03:00 | A8 mit DumpBroken | Kritische Dateien werden klar als fehlend gemeldet |  |  |
| 03:00-04:00 | Syntax-Check | py_compile ohne Fehler |  |  |
| 04:00-05:00 | Build-Readiness | test_build_ready vollständig grün |  |  |

Notfall-Go:
- JA, wenn alle 5 Checks PASS sind.
- NEIN, bei einem einzigen FAIL.
- Wenn möglich innerhalb von 24h den 15-Minuten-Quick-Smoke nachziehen und dokumentieren.
