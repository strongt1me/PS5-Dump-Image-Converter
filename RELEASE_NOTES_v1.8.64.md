# PS5 Dump & Image Converter v1.8.64 – Release Notes

## Zweck dieses Releases

Ein Fehler, den v1.8.63 hätte beheben sollen — gefunden beim Nachmessen am fertigen Programm.

---

## Das Kästchen, das nur beim Start hell war

v1.8.63 hat alle Texte auf der Karte aufgehellt, das Kästchen „Rechner nach erfolgreichem Abschluss herunterfahren" eingeschlossen. Beim Programmstart stimmte die Farbe auch. **Nach dem ersten Wechsel des Farbschemas war sie wieder grau.**

Der Grund: Zwei Stellen setzen dieselbe Eigenschaft. `_apply_caption_colors()` holt die Schriftfarbe aus der Rollentabelle — und unmittelbar danach setzte `_apply_theme()` sie noch einmal fest auf den alten Wert. Der zweite Schreiber gewinnt.

**Im Quelltext war das nicht zu sehen.** Beide Stellen sehen für sich betrachtet richtig aus; erst ihre Reihenfolge macht den Fehler. Aufgefallen ist er beim Messen der Farbe **am lebenden Widget** nach jedem Wechsel:

```
dunkel   Abweichungen: 1 [('Herunterfahren', '#9BA8BA')]
mittel   Abweichungen: 1 [('Herunterfahren', '#A8BFDB')]
hell     Abweichungen: 1 [('Herunterfahren', '#718096')]
```

Danach:

```
dunkel / mittel / hell / dunkel / hell / mittel   Abweichungen: 0
```

---

## Derselbe Fehlertyp, zweimal hintereinander

- **v1.8.62** hellte „PRÜFUNG NACH DEM PACKEN" auf, trug es aber nicht in die Rollentabelle ein.
- **v1.8.63** trug es ein — und übersah, dass für das Kästchen eine zweite Stelle die Farbe erneut setzt.

Beide Male wäre die Änderung beim ersten Wechsel des Farbschemas verschwunden und hätte ausgesehen, als sei sie nie angekommen. Beide Male war der Quelltext unauffällig.

**Deshalb jetzt zwei Prüfungen statt guter Vorsätze:** Eine schaltet durch alle drei Schemata und wieder zurück und misst nach jedem Schritt die Schriftfarbe aller zehn Beschriftungen gegen den Sollwert des dann aktiven Schemas. Die zweite verbietet die überschreibende Zeile ausdrücklich im Quelltext.

Der Wechsel wird **hin und zurück** geprüft, weil ein solcher Fehler nur in einer Richtung auftreten kann.

---

## Tests

**895 Prüfungen, 0 Fehlschläge.** Zwei davon neu.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.64.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.64_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.64_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.64_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.64.sha256` | Prüfsummen aller Quelldateien |
