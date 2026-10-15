# PS5 Dump & Image Converter v1.9.21

## PKG-Erzeugung: neuere eingebaute Bibliothek

Die Bibliothek hinter „Abbild → PKG“ und dem Debug-PKG-Bau wurde auf eine
neuere Fassung aktualisiert. Sie schreibt die innere Struktur der erzeugten Debug-Pakete
an mehreren Stellen so, wie es die Konsole erwartet – unter anderem die Ausrichtung
des inneren Dateisystem-Kopfes, die Reihenfolge der Struktur-Prüfsummen und die
Blockzuordnung. Das kann die Chance erhöhen, dass ein gebautes Paket auf der Konsole
angenommen wird. An der Bedienung des Programms ändert sich nichts.

Hinweis: Ob damit ein bestimmter Startfehler auf der Konsole verschwindet, zeigt erst
der Test auf echter Hardware.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.21.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.21_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.21_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.21.sha256` listet die SHA-256 aller Quelldateien.
