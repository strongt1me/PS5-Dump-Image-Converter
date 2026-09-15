# PS5 Dump & Image Converter v1.9.20

## Neu: „ffpfsc → ffpfsc“ mit Asset-Pack (Aufgabe 2 „ffpfsc konvertieren“)

Eine `.ffpfsc` lässt sich jetzt wieder zu einer `.ffpfsc` machen – aber nur, wenn
**AMPR EMU Asset-Pack** ausgewählt ist. Ohne Asset-Pack bleibt diese Auswahl
ausgeblendet, weil ein bloßes Umpacken nichts brächte. Ist das Asset-Pack gewählt,
läuft beim Start alles in einem Zug: die `.ffpfsc` wird in einen Dump-Ordner entpackt,
das Asset-Pack wird darin aufgebaut und eingebaut, und daraus entsteht eine neue `.ffpfsc`
**inklusive Asset-Pack** – ohne Zwischenfrage.

## Behoben

- **Einfrieren/Abbruch beim Starten** behoben: Wenn vor dem Start die Platzabfrage
  erschien (z. B. bei `.ffpkg → .ffpfsc` mit AMPR EMU), brach das Programm ab. Das ist
  behoben; auch zwei Bibliotheks-Fenster waren davon betroffen.
- **Einstellungen mit BOM**: Eine mit einem BOM gespeicherte Einstellungsdatei wird wieder
  korrekt gelesen und nicht mehr überschrieben. Eine beschädigte Datei wird gesichert
  statt still ersetzt, und der Doktor weist darauf hin.
- **Sichtbarer Fortschritt**: Die Abschlussprüfung und das Entpacken einer `.ffpkg` zeigen
  jetzt einen Fortschritt statt minutenlangem Stillstand; das Entpacken lässt sich abbrechen.
- **Sammelkonvertierung**: Zwei gleichnamige Quellen (z. B. `Spiel.exfat` und `Spiel.ffpkg`)
  überschreiben sich nicht mehr gegenseitig; die zweite wird mit Hinweis übersprungen.
- **exFAT-Laufwerke**: Beim Prüfen nach dem Packen wird nicht mehr die ganze Quelle daneben
  kopiert.
- **„PKG lesen“**: Der Hinweis zu verschlüsselten Inhalten wurde für Debug-Pakete
  richtiggestellt.
