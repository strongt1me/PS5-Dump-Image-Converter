# PS5 Dump & Image Converter v1.9.27

Zwei Korrekturen rund um den AMPR EMU: PlayGo lässt sich jetzt einschalten,
solange es noch etwas nützt, und die Sicherung der Originalbibliothek sichert
kein falsches Original mehr.

## PlayGo: gefragt wird vor der Arbeit, nicht danach

Manche Spiele erklären PlayGo-Inhalte – Sprach- oder Szenariopakete, erkennbar
an `sce_sys/playgo-scenario.json`. Ohne den PlayGo-Stub warten sie unter
Umständen auf Pakete, die nie kommen, und starten nicht. Bisher kam der Hinweis
darauf zu spät: bei einem Dump-Ordner als Meldung mit nur „OK“, bei einem
Abbild erst im Protokoll, nachdem es ausgepackt war.

Jetzt fragt das Programm am Anfang des Laufs, bevor kopiert, entpackt oder
gepackt wird: **„PlayGo einschalten?“** Vorbelegt ist *Ja* – das Kästchen wird
angehakt, und der Stub kommt gleich mit ins Ergebnis.

Bei `.exFAT`, `.ffpfsc` und `.ffpfs` sieht das Programm dafür ins Verzeichnis
des Abbilds, ohne auszupacken – in Sekundenbruchteilen, auch bei sehr großen
Spielen. In ein `.ffpkg` lässt sich so nicht hineinsehen; dort kommt die Frage,
sobald die Dateien ausgepackt daliegen, und immer noch vor dem Bau des
Ergebnisses. Kommandozeile und Sammelkonvertierung fragen nie; dort steht ein
Hinweis im Protokoll.

## Keine falsche `.orig`-Sicherung mehr

Beim Einbau des AMPR EMU wird eine vorhandene Bibliothek als `.orig` gesichert.
Lag dort schon ein AMPR EMU aus einem früheren Einbau, wurde dieser als
„Original“ gesichert – im fertigen Abbild lag eine `libSceAmpr.sprx.orig`, die
in Wahrheit der Emulator war. Emulatoren und PlayGo-Stubs werden jetzt am Inhalt
erkannt und nicht mehr gesichert; echte Originale weiterhin. Das gilt für den
Einbau beim Erstellen, für Aufgabe 7 und für die Fenster „AMPR EMU – alte/neue
Methode“.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.27.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.27_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.27_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.27.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
