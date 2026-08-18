# PS5 Dump & Image Converter v1.8.30 – Release Notes

## Zweck dieses Releases

Version **v1.8.30** bringt eine neue Funktion: Der Rechner fährt nach einer erfolgreich abgeschlossenen Aufgabe von allein herunter. Große Konvertierungen laufen damit unbeaufsichtigt zu Ende.

Die Bedingung dafür ist die eigentliche Arbeit an dieser Funktion: Nach einem Fehler oder Abbruch bleibt der Rechner an, damit die Meldung lesbar bleibt – und heruntergefahren wird erst, wenn gemountete Abbilder gelöst und die temporären Ziele geräumt sind.

## Änderungen im Einzelnen

### 1. Woran „erfolgreich" festgemacht wird

Maßgeblich ist ausschließlich `_last_task_ok`. Dieses Flag setzt `_write_task_report()` bei jedem Aufgabenende auf `bool(success) and not aborted` – auf allen vier Wegen (Erfolg, Abbruch, Fehler, Ausnahme). Der CLI-Modus leitet daraus schon seit v1.8.25 seinen Exit-Code ab.

Bewusst **nicht** ausgewertet wird der Statustext. Er ist übersetzt, und genau diese Textsuche hatte im CLI-Modus schon einmal Fehlläufe unter englischer Spracheinstellung als Erfolg durchgehen lassen. Ein eigener Test hält das fest: Ein Statuslabel mit dem Text „Completed successfully" darf die Entscheidung nicht beeinflussen.

Die Regel steht in `_should_shutdown_after_task()` und ist frei von Nebenwirkungen und Oberflächenzugriffen, damit sie für sich prüfbar ist. Sie verlangt vier Dinge gleichzeitig: Einstellung aktiv, `is_running` False, `_last_task_ok` True, kein bereits laufender Countdown.

Aufgabe 5 (Sammelkonvertierung) braucht keine Sonderbehandlung: Die Schleife über die Einzelquellen läuft innerhalb von `_run_flexible_conversion()`, `_write_task_report()` wird danach genau einmal aufgerufen. Ein Start = ein Ergebnis = eine Entscheidung.

### 2. Reihenfolge vor dem Herunterfahren

`_shutdown_cleanup_and_execute()` geht denselben Weg wie `on_closing()` beim normalen Beenden – nur dass am Ende der Herunterfahr-Befehl steht statt `root.destroy()`:

1. Laufzeitflags zurücksetzen (`is_running`, `monitor_active`, `_engine_done_event`).
2. `_force_dismount_all()` – sonst bleiben OSFMount-/Dokan-Laufwerke hängen.
3. `_cleanup_exit_temp_targets()` – sonst bleiben pro Lauf mehrere hundert MB liegen.
4. Protokoll-Handler leeren, damit im Logfile steht, warum der Rechner ausging.
5. `shutdown.exe /s /t 0 /f`.

Ein Fehler beim Aufräumen hält das Herunterfahren nicht auf (er wird protokolliert); ein fehlgeschlagener Herunterfahr-Befehl dagegen löst die Sperre wieder, schließt das Countdown-Fenster und lässt den Rechner an.

### 3. Countdown mit Abbruch

Vor dem Herunterfahren erscheint ein Fenster mit 60-Sekunden-Countdown, großem Abbrechen-Knopf, ESC-Bindung und Abbruch auch beim Schließen des Fensters.

Der Countdown läuft bewusst im Programm und nicht über `shutdown /t 60`: Bei der Windows-Variante ginge der Abbruch nur über `shutdown /a` in einer Konsole, und Windows blendete ein eigenes Hinweisfenster ein. So greift der Abbruch sofort, und das Fenster kann erklären, was gleich passiert – einschließlich des Hinweises, dass `/f` auch andere Programme ohne Rückfrage beendet.

### 4. Keine Erfolgsmeldung bei aktiver Funktion

Der Abschlussdialog („Aufgabe erfolgreich abgeschlossen") entfällt, solange das Ankreuzfeld gesetzt ist. Er würde auf eine Bestätigung warten, die niemand gibt – der Sinn der Funktion ist ja, den Rechner allein zu lassen. Der Erfolg steht weiterhin in Statuszeile und Protokoll.

### 5. Bedienung, Speicherung, CLI

Das Ankreuzfeld sitzt in der Quelle-Karte unter TEMP-ORDNER. Bewusst dort und nicht in der Aktionsleiste: Ein `tk.Checkbutton` zeichnet immer seine Hintergrundfarbe, auf dem Hintergrundbild wäre das wieder einer der Kästen, die seit v1.8.28 verschwunden sind. In der Karte liegt ohnehin eine Fläche.

Die Wahl wird über `_save_setting`/`_load_setting` dauerhaft gespeichert und beim Design-Wechsel mit umgefärbt. Alle neuen Texte liegen als Schlüssel in `ps5_validator/utils/i18n.py` in beiden Sprachen vor.

Im Kommandozeilenmodus schaltet `--shutdown-on-success` die Funktion ein; dort entscheidet allein der Schalter, nicht die gespeicherte Wahl aus der Oberfläche. Das Herunterfahren läuft dort direkt und blockierend statt über den Countdown – der Poll des CLI-Modus beendet die Ereignisschleife, sobald der Aufgaben-Thread durch ist, ein eingeplantes Fenster käme nicht mehr zum Zug. Der Exit-Code bleibt unverändert das Ergebnis der Aufgabe.

## Bedeutung für Nutzer

- Lange Konvertierungen können über Nacht laufen, ohne dass der Rechner danach weiterläuft.
- Geht etwas schief, steht der Rechner am nächsten Morgen noch mit der Meldung da.
- Ergebnisse und Temp-Ordner sind vor dem Ausschalten sauber abgeschlossen.

## Verifikation

- `test_shutdown_after_task.py` (neu): 14 Tests über die Entscheidungsregel (Erfolg, Fehler, Abbruch, laufende Aufgabe, abgeschaltete Einstellung, doppelter Countdown, Statustext ohne Einfluss), die Reihenfolge Lösen → Räumen → Herunterfahren, das Verhalten bei fehlgeschlagenem Befehl und bei Fehlern beim Aufräumen sowie den Vorrang von Ankreuzfeld und CLI-Schalter. Der echte Befehl wird dabei nie abgesetzt.
- An der laufenden Oberfläche geprüft (mit abgefangenem Befehl): Ankreuzfeld vorhanden und aus, bei fehlgeschlagener Aufgabe startet kein Countdown, bei erfolgreicher erscheint das Fenster „Herunterfahren", ESC bricht ab, danach ist die Sperre wieder gelöst und das Fenster geschlossen.
- Gesamte Testauswahl: 40/40 bestanden (`test_background_image`, `test_i18n`, `test_ini_config`, `test_build_ready`, `test_all_quality`, `test_all_quality_new`, `test_shutdown_after_task`); `test_build_ready.py` zusätzlich 8/8 als Build-Freigabe.

**Noch offen:** Ein echter Durchlauf bis zum tatsächlichen Herunterfahren wurde nicht ausgeführt – dafür müsste der Rechner ausgehen.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.30** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.30.sha256`

Neu im Projekt: `test_shutdown_after_task.py`.
