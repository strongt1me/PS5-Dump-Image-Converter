# PS5 Dump & Image Converter v1.7.87

## Zusammenfassung

Version **v1.7.87** korrigiert die nicht synchrone Fortschrittsanzeige während der `.ffpkg`-Erstellung. Die Oberfläche verarbeitet jetzt den echten 0–100-%-Ausgabestrom von UFS2Tool `makefs` ohne Pufferverzögerung und aktualisiert Balken, Prozentlabel, Datei-/Bytezähler sowie die interne ProgressEngine aus derselben Quelle.

Während der vollständigen End-to-End-Prüfung wurde zusätzlich ein unabhängiger Fehler im Imagegrößenprofil reproduziert: Bei sehr vielen kleinen Dateien reichte die bisherige Reserve trotz geringer Rohdatenmenge nicht aus, weil UFS2 jede Datei im verwendeten Profil auf ein Fragment von bis zu 64 KiB aufrunden kann. v1.7.87 reserviert diese maximal mögliche Fragmentaufrundung nun pro Datei.

> Eine `.ffpkg` gilt im Produktionspfad weiterhin erst dann als erfolgreich, wenn UFS2Tool `info` und die schreibgeschützte Prüfung `fsck_ufs -fn` bestanden wurden. Erst danach wird die temporäre `.part`-Datei atomar als endgültige Ausgabe übernommen.

## Behobene Ursachen

| Bereich | Ursache vor v1.7.87 | Korrektur in v1.7.87 |
|---|---|---|
| Live-Fortschritt | UFS2Tool überschreibt Fortschrittszeilen mit `\r`; normale Text-Zeileniteration konnte diese Ereignisse bis zu einem Zeilenende oder Prozessende puffern. | Der Callback-Pfad liest stdout binär und ungepuffert und trennt sofort an `\r` oder `\n`. |
| GUI-Synchronität | Fortschrittsquelle, sichtbarer Balken und ProgressEngine wurden nicht aus einem gemeinsamen UFS2Tool-Ereignis gespeist. | Eine thread-sichere Queue transportiert Start-, Live- und Endereignisse; ausschließlich der Tkinter-Hauptthread aktualisiert alle sichtbaren und internen Werte. |
| Falsches Weiterzählen | Pulse-Fallbacks oder alte MkPFS-Werte konnten den sichtbaren Buildfortschritt überlagern. | Während `makefs` aktiv ist, sind Pulse-Creep und fremde Enginewerte unterdrückt; der letzte echte Wert bleibt stabil. |
| Viele Kleindateien | Die Größenformel berücksichtigte Rohdaten, Inodes und Metadaten, aber nicht die maximal mögliche 64-KiB-Fragmentaufrundung jeder Datei. | Zusätzlich wird `Dateianzahl × (64 KiB − 1)` als konservative Fragmentreserve berücksichtigt. |
| Ressourcenfreigabe | Pipe-Handles des Callback-Prozesses konnten nach kurzen Testprozessen verspätet freigegeben werden. | stdout und stdin werden in Erfolgs-, Abbruch- und Fehlerpfaden zuverlässig geschlossen. |

## Sichtbares Verhalten

Während UFS2Tool `makefs` läuft, zeigt die Oberfläche beispielsweise folgenden zusammenhängenden Zustand:

```text
FFPKG: 37.0% | 8/20 Dateien | 378.9 KiB/1.0 MiB
```

Der sichtbare Prozentwert ist der echte UFS2Tool-Wert. Derselbe Wert wird linear auf den festgehaltenen FFPKG-Buildschritt abgebildet. Zwischen zwei UFS2Tool-Ereignissen wird nicht künstlich weitergezählt.

## End-to-End-Verifikation der `.ffpkg`-Erstellung

Vier unterschiedliche Quellen wurden mit der tatsächlich eingebetteten UFS2Tool-v4.1-DLL gebaut. Jeder Rundlauf umfasste `makefs`, `info`, `fsck_ufs -fn`, vollständige Extraktion und einen SHA-256-Vergleich jeder extrahierten Datei mit der Quelle.

| Testfall | Quelldateien | Quellbytes | FFPKG-Größe | Buildzeit | Erstes Live-Ereignis | Ereignisse | Ergebnis |
|---|---:|---:|---:|---:|---:|---:|---|
| Gemischter Verzeichnisbaum | 164 | 7.385.265 | 155.058.176 | 0,183 s | 0,139 s | 102 | PASS |
| 5.000 Kleindateien | 5.000 | 400.000 | 544.276.480 | 0,634 s | 0,192 s | 102 | PASS |
| Große Binärdateien | 3 | 135.267.124 | 269.746.176 | 0,302 s | 0,167 s | 102 | PASS |
| Cylinder-Group-Grenzfall | 2.050 | 649.068.901 | 973.733.888 | 1,126 s | 0,161 s | 102 | PASS |
| **Gesamt** | **7.217** | **792.121.290** | **1.942.814.720** | — | **max. 0,192 s** | **408** | **PASS** |

Für alle vier Testfälle gelten zusätzlich folgende Integritätsnachweise:

| Prüfung | Ergebnis |
|---|---|
| `makefs` Exit-Code | 0 |
| UFS2Tool `info` Exit-Code | 0 |
| `fsck_ufs -fn` Exit-Code | 0 |
| Vollständige Extraktion Exit-Code | 0 |
| Fehlende Dateien | 0 |
| Unerwartete Dateien | 0 |
| Dateien mit abweichendem SHA-256 | 0 |
| Fortschritt monoton | Ja |
| Fortschritt erreicht 100 % | Ja |

Der 5.000-Kleindateien-Fall scheiterte mit dem vorherigen Größenprofil reproduzierbar wegen fehlenden Imageplatzes. Nach Ergänzung der Fragmentreserve bestand derselbe Fall vollständig. Der große Cylinder-Group-Fall zeigte bei `fsck_ufs -fn` keine Superblock-, Bitmap- oder Cylinder-Group-Fehler.

## Produktions- und GUI-Nachweise

Der separate Test-Harness war nicht der einzige geprüfte Pfad. Zusätzlich wurde der produktive `_build_ffpkg_from_folder`-Ablauf direkt mit der eingebetteten UFS2Tool-v4.1-DLL ausgeführt.

| Nachweis | Ergebnis |
|---|---|
| Produktive `.part`-Erstellung | PASS |
| Produktionsaufruf von `info` und `fsck_ufs -fn` | PASS |
| Atomare Übernahme zur finalen `.ffpkg` | PASS |
| Queue-Ereigniskette von 0 bis 100 % | PASS |
| Queue → Schrittfortschritt → Balken → Prozentlabel → Detailtext im selben GUI-Takt | PASS |
| Vollständige Tkinter-Initialisierung und Eventloop | PASS |
| Hauptprogrammstart unter Xvfb, kontrollierter SIGTERM nach 8 s | PASS, Status 143 |

## Regression und Build-Bereitschaft

| Testgruppe | Ergebnis |
|---|---|
| Automatische Unit-/Regressionserkennung | 17 PASS, 1 opt-in Integrationsfall planmäßig übersprungen |
| Opt-in Produktionsintegration | 1/1 PASS |
| FFPKG-Buildhilfen einschließlich Kleindateienreserve | 10/10 PASS |
| FFPKG-Fortschrittsparser und Live-`\r`-Callback | 4/4 PASS |
| Eingebettetes UFS2Tool-v4.1-Laufzeitpaket | 3/3 PASS |
| Moderne Quality Suite | 14/14 PASS |
| Legacy Quality Suite | 7/7 PASS |
| Python-Syntaxprüfung | PASS unter Python 3.11 und 3.12 |
| Build-Readiness | 7/7 PASS |

Die verifizierten `.ffpfsc`-Erstellungsfunktionen und der vorgeschriebene MkPFS-Packaufruf wurden durch diesen Fix nicht verändert.

## Windows-EXE bauen

Das vollständige Projektarchiv entpacken und in PowerShell im Projektordner ausführen:

```powershell
.\Build_EXE.ps1
```

Der synchronisierte Zielname lautet:

```text
dist\PS5_Dump_Image_Converter_v1.7.87.exe
```

Anwendungsversion, PyInstaller-Spezifikation, Windows-Dateiversionsressource, Buildskript, README und Build-Readiness-Test verwenden konsistent **v1.7.87**.

## Relevante Prüfdateien

| Datei | Zweck |
|---|---|
| `test_ffpkg_progress_sync.py` | Parser, `\r`-/`\n`-Zerlegung und ungepufferter Live-Callback |
| `test_ffpkg_build_support.py` | UFS2-Profil, Größenformel und 64-KiB-Fragmentreserve |
| `test_ffpkg_production_integration.py` | Produktiver GUI-Builder mit eingebetteter UFS2Tool-DLL |
| `tools/ffpkg_e2e_verify.py` | Reproduzierbare Build-, Prüf-, Extraktions- und SHA-256-Rundläufe |
| `tools/gui_smoke_test.py` | Vollständiger GUI-Start und Queue-zu-Widget-Synchronisation |
