# PS5 Dump & Image Converter v1.9.28

Zwei Treiberprüfungen, die „vorhanden“ meldeten, wo „einsatzbereit“ gemeint
war – und eine Anleitung, auf die ein Knopf schon immer zeigte.

## OSFMount: der Treiber zählt, nicht nur das Programm

OSFMount braucht das Programm seit v1.9.25 nicht mehr; der eingebaute
exFAT-Leser kommt ohne aus. Als Rückfall für ungewöhnliche Abbilder kann es
aber einspringen, und dafür muss sein Treiber `osfdisk` installiert sein.
Bisher meldete der Diagnosebericht „vorhanden“, sobald OSFMount gefunden war –
auch wenn der Treiber fehlte und OSFMount damit nichts einhängen konnte.

Jetzt sieht das Programm nach, nur lesend und ohne Administratorrechte: Dienst,
Treiberpaket, Treiberdatei und Gerät. Im Abschnitt *Fremdwerkzeuge* des
Diagnoseberichts steht dann „bereit“ oder genau, was fehlt, samt Abhilfe. Auch
**OSFMount installieren** prüft den Treiber mit: Bei fehlendem Treiber meldete
der Knopf bisher „bereits installiert und einsatzbereit“ und tat nichts.
Scheitert die Einrichtung, nennt das Fehlerfenster jetzt den Grund.

## Dokan: nur Dokan 2 gilt

Einige Wege mit `.ffpkg` hängen das Abbild unter Windows über UFS2Tool ein und
brauchen dafür den Treiber Dokan 2. Die Prüfung ließ bisher auch einen Treiber
aus Dokan 1 gelten, wenn daneben die Bibliothek von Dokan 2 lag – die arbeitet
aber nur mit ihrem eigenen Treiber. In diesem Mischzustand galt Dokan als
vorhanden, **Dokan2-Treiber installieren** tat nichts, und das Einhängen
scheiterte trotzdem. Jetzt zählen nur Treiber und Bibliothek von Dokan 2
zusammen.

## Die Anleitung zur neuen Methode ist da

Im Fenster hinter Knopf 7 hat jede der beiden AMPR-Methoden einen Knopf
**Anleitung**. Bei der neuen Methode meldete er bisher immer, die Anleitung
fehle. Jetzt öffnet er eine Anleitung für ShadowMountPlus ab 1.7 alpha8,
geprüft am Quellcode der mitgelieferten Fassung 1.7 alpha13fix1: wo gesucht
wird, wie der Cache aus Spiel-, globaler und Emulator-Bibliothek entsteht und
wer bei gleichem Dateinamen gewinnt, alle Einstellungen, acht Stolperfallen,
die Protokollzeilen und woran sich erkennen lässt, welche Fassung auf der
Konsole läuft.

Zwei Punkte daraus betreffen den AMPR EMU direkt: Dateien aus
`/data/shadowmount/emus` ersetzen nur, was das Spiel schon mitbringt – ohne
`libSceAmpr.sprx` im Spiel bewirken sie nichts. Und mit
`global_fakelib_priority=global` gewinnt eine ältere `libSceAmpr.sprx` im
globalen Ordner auch gegen eine frisch aktualisierte.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.28.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.28_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.28_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.28.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
