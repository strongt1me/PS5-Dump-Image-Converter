# PS5 Dump & Image Converter v1.8.65 – Release Notes

## Zweck dieses Releases

Ein Absturz im Hintergrund, gefunden bei einem Durchgang durch **alle 26 Werkzeugfenster** am fertigen v1.8.64.

---

## Der Fehler, den niemand sehen konnte

Das **Bibliotheksfenster** durchsucht die eingetragenen Ordner in einem eigenen Arbeitsfaden und meldet das Ergebnis danach ins Fenster zurück. Wird das Fenster in der Zwischenzeit geschlossen — also genau das, was man tut, wenn die Suche zu lange dauert —, wirft Tk:

```
RuntimeError: main thread is not in main loop
```

Der Faden endet mitten in seiner Arbeit. Am Programm ist davon **nichts zu bemerken**: Es läuft weiter, nichts geht verloren. Nur im Fehlerbericht steht seit v1.8.58 ein Absturz — einer, der keiner ist, und der bei der Fehlersuche in die Irre führt.

Dasselbe galt für den **Protokollempfänger des JS-Loaders**: Er nimmt weiter Zeilen von der Konsole entgegen, auch wenn niemand mehr hinsieht.

---

## Warum nur zwei Stellen geändert wurden

Es gibt **19 Stellen**, an denen ein Arbeitsfaden über `win.after(0, …)` ins Fenster zurückmeldet. Siebzehn davon liegen in einem `try`-Block und gehen glimpflich aus — dort wäre eine Änderung reine Beschäftigung.

Die beiden ungeschützten gehen jetzt über einen gemeinsamen Weg, der vorher nachsieht, ob es das Fenster überhaupt noch gibt. Er verschluckt auch den Fall, dass das Fenster **zwischen** der Prüfung und dem Eintragen verschwindet.

---

## Der Test, der ihn wirklich prüft

Fünf neue Prüfungen. Die wichtigste stellt den Fall **aus einem echten Arbeitsfaden** nach:

> Im Hauptfaden wirft Tk gar nicht. Ein Test dort wäre grün gewesen und hätte den Fehler trotzdem durchgelassen.

Dazu eine Prüfung, die verbietet, an der Stelle im Bibliotheksfenster wieder direkt `after()` zu rufen.

---

## Was der Durchgang sonst ergab

Alle 26 Fenster wurden geöffnet und wieder geschlossen: **0 Tk-Fehler, 0 vom Programm selbst festgehaltene Fehler.** Die Fenster, die nichts anzeigten, brauchen erst eine Quelle oder eine Auswahl — das ist ihr Normalverhalten.

Zusätzlich geprüft: Die Prüfsummenliste deckt sich mit dem Arbeitsordner (245 Einträge, 0 Abweichungen).

---

## Tests

**900 Prüfungen, 0 Fehlschläge.** Fünf davon neu.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.65.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.65_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.65_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.65_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.65.sha256` | Prüfsummen aller Quelldateien |
