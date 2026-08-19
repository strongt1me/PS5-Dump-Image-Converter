# PS5 Dump & Image Converter v1.8.55 – Release Notes

## Zweck dieses Releases

Vier Befunde von echter Apple-Hardware (Mac mini M1, macOS 26.6.2), dazu eine Feststellung für gemischte Monitor-Skalierungen. Der schwerste Befund war ein vollständiger Absturz – und sein Bericht führte zu einer zweiten Stelle mit derselben Ursache, die niemand gemeldet hatte.

---

## 1. Der Absturz beim Klick auf FileZilla

Der Absturzbericht benennt die Stelle genau:

```text
Exception Reason: *** -[__NSArrayM insertObject:atIndex:]: object cannot be nil
3  libtk8.6.dylib   setAllowedFileTypes + 268
4  libtk8.6.dylib   Tk_GetOpenFileObjCmd + 1240
```

`Tk_GetOpenFileObjCmd` ist `askopenfilename`. Der Dialog wurde mit dieser Musterliste aufgerufen:

```python
filetypes=[("FileZilla", "filezilla.exe"), ("EXE-Dateien", "*.exe")]
```

Tk streift von jedem Muster führende `*` und `.` ab und reicht den Rest als **Dateiendung** an macOS weiter. Aus `*.exe` wird `exe` – gültig. Aus `filezilla.exe` wird `filezilla.exe`, und das ist keine Endung: macOS liefert dafür nichts zurück, Tk legt das Nichts in ein Array, Objective-C bricht den Prozess ab. Kein Python-Fehler, deshalb keine Meldung – nur `SIGABRT` und der Apple-Fehlerbericht.

### Die zweite Stelle

Weil die Regel damit feststand, ließen sich alle 24 Dateidialoge danach durchsuchen. Der SELF-Inspektor führte:

```python
(…, "eboot.bin *.self *.sprx *.prx *.elf *.bin")
```

**Derselbe Fehler, unentdeckt.** `*.bin` deckt die Datei ohnehin mit ab; der Eintrag ist raus.

### Damit es keine dritte gibt

`_dateitypen()` entschärft eine Musterliste auf macOS und lässt sie auf Windows und Linux unangetastet – dort sind Dateinamen als Muster erlaubt und nützlich. Der Absturzbericht steht im Docstring.

Dazu eine Prüfung, die den Quelltext per AST durchgeht und **jeden** `filetypes=`-Aufruf beanstandet, dessen Muster einen Dateinamen enthält, sofern er nicht durch `_dateitypen` gereicht wird. Sie läuft unter Windows und braucht keinen Mac.

Am Rande: `*.*` ist unbedenklich. Nach dem Abstreifen bleibt nichts übrig, und was leer ist, überspringt Tk – die 21 „Alle Dateien"-Einträge im Programm sind sicher.

---

## 2. FileZilla wurde auf dem Mac nie gefunden

Gesucht wurde ausschließlich `filezilla.exe` – in Windows-Pfaden, in der Windows-Registrierung und über alle festen Laufwerke. Auf einem Mac mit installiertem FileZilla meldete das Programm deshalb „nicht gefunden" und bot an, die **Windows-Fassung** herunterzuladen.

Jetzt gibt es einen eigenen Weg für macOS und Linux: `/Applications/FileZilla.app`, das Benutzer-Programmverzeichnis, Homebrew-Pfade, Flatpak und `which`. Gestartet wird ein Bündel mit `open -a` – ausführen lässt es sich nicht, es ist ein Ordner.

Ebenfalls behoben: Ein gemerkter Pfad auf ein `.app` fiel bei jeder Prüfung durch `os.path.isfile()`. Die Suche begann bei jedem Start von vorn, selbst nach einer manuellen Auswahl.

---

## 3. Das Hintergrundbild – zwei Ursachen

**Im Vollbild wurde es gar nicht angepasst.** In zwei Funktionen stand `or self.is_fullscreen`; das Bild behielt die Größe aus dem Fenstermodus, während Inhaltsfläche, Seitenleiste und Karten ihre Bilder nachzogen. An einem großen Monitor passte hinterher nichts mehr zusammen. Beim Verlassen des Vollbilds kam ein `<Configure>` – das Bild „fing sich wieder", genau so gemeldet.

**Und es wurde grundsätzlich gestreckt.** An acht Stellen stand `resize((breite, höhe))`. Bei abweichendem Seitenverhältnis verzerrt das sichtbar; der Einstellungsdialog sagte es sogar an. Auf einem 16:9-Schirm fällt es nie auf, auf einem breiten sofort.

Jetzt füllt das Bild formatfüllend und wird mittig beschnitten, wie ein Bildschirmhintergrund.

**Warum das gefahrlos ging:** Die neue Skalierung liefert **exakt dieselben Ausgabemaße**. Alle Ausschnitte, die die eingebrannten Beschriftungen aus dem skalierten Bild schneiden, rechnen unverändert weiter – und bei passendem Seitenverhältnis, dem Normalfall mit den mitgelieferten Bildern, ist das Ergebnis Pixel für Pixel identisch mit vorher. Ein Test hält beides fest.

---

## 4. Schrift und Knöpfe auf macOS

Die 264 Schriftangaben im Programm stehen in **Punkt**, und was ein Punkt in Pixeln bedeutet, entscheidet `tk scaling`. Gemessen unter Windows bei 125 % Anzeigeskalierung: **1,668** – eine 9-Punkt-Schrift wird 15 Pixel hoch. Aqua rechnet mit 72 dpi, dieselbe Angabe ergibt dort **9 Pixel**. Dazu ist die Systemschrift von macOS 13 Punkt groß, die von Windows 9 – die Zahlen im Quelltext sind an Windows geeicht.

Ein einziger `tk scaling`-Aufruf beim Start hebt alle Punktgrößen zugleich; Knöpfe wachsen mit, weil ttk sie nach Textgröße plus Polsterung bemisst. Die Alternative wären 264 Zahlen im Quelltext gewesen.

**Der Faktor 1,35 ist ein erster Vorschlag, kein Messergebnis.** Er liegt zwischen dem reinen dpi-Ausgleich (1,333) und dem Verhältnis der Systemschriften (1,444), bewusst eher vorsichtig: Zu große Schrift sprengt Bedienelemente mit fester Pixelbreite, und das wäre schlimmer als zu kleine.

**Ohne neuen Bau änderbar:** Schlüssel `macos_font_scaling` in der Einstellungsdatei, Werte zwischen 0,5 und 4,0.

---

## 5. Monitorwechsel mit anderer Skalierung

Tk 8.6 liest die DPI einmal beim Start und verarbeitet `WM_DPICHANGED` nicht; ein virtuelles Ereignis dafür gibt es nicht. Zieht man das Fenster auf einen Monitor mit anderer Skalierung, bleibt es in Pixeln unverändert und wirkt zu klein oder zu groß – in sich aber stimmig.

**Behoben wird das nicht, festgehalten schon.** Ein Ausgleich müsste 274 Schriftangaben, 96 feste `width`/`height`, 292 feste Abstände und sämtliche Bilder zugleich nachziehen. Nur die Schriften zu vergrößern ergäbe abgeschnittene Beschriftungen in unveränderten Kästen – schlechter als der jetzige Zustand.

Die Feststellung kostet 0,60 Mikrosekunden je Aufruf und schreibt eine Zeile nach `%TEMP%\ps5converter.log`. Ein Test bewacht, dass sie nichts umrechnet.

---

## Tests

**797 Prüfungen, 0 Fehlschläge.** Neu: die AST-Prüfung über alle Dateidialoge, sechs Prüfungen zur formatfüllenden Skalierung, fünf zur Schriftskalierung, fünf zur FileZilla-Suche und fünf zur DPI-Feststellung.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.55.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.55_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.8.55.sha256` | Prüfsummen aller Quelldateien |
