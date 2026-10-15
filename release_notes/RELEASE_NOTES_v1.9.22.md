# PS5 Dump & Image Converter v1.9.22

## Neu: Dump-Ordner in den Arbeitsordner statt zum Ziel

In der Pfad-Karte gibt es ein neues Häkchen: **„Dump-Ordner im Arbeitsordner
statt beim Ziel anlegen“**. Die Umpack-Wege (z. B. `ffpfsc → ffpkg`,
`ffpkg` neu packen, `Abbild → ffpfsc` mit AMPR-EMU-/BACKPORT-Einbau) entpacken
die Quelle vor dem Neubau in einen vorübergehenden Dump-Ordner. Bisher lag
dieser beim Ziel; mit dem Häkchen wandert er in den Arbeitsordner, sodass am
Ziel-Laufwerk nur das fertige Ergebnis entsteht und dort nichts
zwischengespeichert wird.

Voreinstellung ist **aus** – das bisherige Verhalten ändert sich nicht.
Reine Entpack-Aufgaben sind nicht betroffen: Dort ist der Dump-Ordner das
Ergebnis und bleibt am Ziel.

Hinweis: Bei eingeschaltetem Häkchen muss der **Arbeitsordner** den
vollständigen Dump fassen (mehrere zig GB). Auf der Kommandozeile bewirkt
`--dump-im-arbeitsordner` dasselbe; ohne den Schalter gilt die im Fenster
gespeicherte Einstellung.

## Behoben: Asset-Pack-Bau mit Sonderzeichen im Titel

Enthielt der Spielname ein Zeichen ausserhalb der westlichen
Windows-Zeichentabelle – etwa das „ō“ in „Ghost of Yōtei“ –, brach der
Einbau des Asset-Packs ganz am Ende mit einem Kodierungsfehler ab
(„'charmap' codec can't encode“). Das ist behoben; solche Titel lassen sich
jetzt mit Asset-Pack bauen.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.22.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.22_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.22_linux_x86_64
  ```

  Benötigt keine Python-Installation. Aufgaben, die OSFMount, Dokan oder UFS2Tool brauchen, laufen nur unter Windows – das Programm sagt das beim Start einer solchen Aufgabe.
- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.22.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
