# PS5 Dump & Image Converter v1.9.29

Ein neues Werkzeug für den NOR-Flash der Konsole – und die eigene Lizenz, die
seit Juli fehlte.

## Neu unter WEITERE TOOLS: PS5 Wee Tools

**PS5 Wee Tools** von andy-man (GPL-3.0, Fassung 0.1.8) kommt jetzt mit. Es
arbeitet nicht mit Spiel-Dumps, sondern mit dem NOR-Flash der Konsole: Es liest
aus einem NOR-Dump Modell, SKU, Region, Seriennummern, Firmware und
MAC-Adressen, zerlegt den Dump in seine Partitionen und setzt ihn wieder
zusammen, zeigt das UART-Protokoll samt EMC-Fehlercodes und kann über einen
SPI-Flasher (SPIway auf einem Teensy 2.0) den NOR lesen und beschreiben.

Zu finden unter **WEITERE TOOLS → PS5 Wee Tools (NOR)**. Vor dem Start fragt
das Programm nach, vorbelegt ist *Nein* – ein falsch beschriebener NOR kann die
Konsole unbrauchbar machen. Danach öffnet sich das Werkzeug in einem eigenen
Konsolenfenster, unter Linux und macOS in einem Terminal, und übernimmt beim
ersten Start die Sprache des Programms. Bis das Fenster steht, kann es bis zu
einer Minute dauern – unter Windows und Linux entpackt sich die Programmdatei
dafür ein zweites Mal. Gelesene Dumps und UART-Protokolle
landen im Ordner `PS5 Wee Tools` neben dem Programm, unter macOS im
Einstellungsordner.

Das Werkzeug liegt unverändert bei; Quelltext, Lizenz und Herkunft stehen im
Ordner `PS5-Wee-Tools-0.1.8`. Der Diagnosebericht führt es mit Fassung und
Quelle unter dem, was mitgeliefert wird.

## Die Lizenz des Programms liegt wieder bei

Das Programm steht unter der MIT-Lizenz. Die Datei `LICENSE` mit ihrem Text
fehlte seit Juli im Repo und damit in jeder gebauten Fassung. Jetzt liegt sie
wieder im Repo und steckt in jeder gebauten Fassung. Der Lizenztext, den das
Programm unter Windows beim Start in die Registry schreibt, nennt jetzt
denselben Inhaber und dasselbe Jahr wie die Datei.

## Kleinigkeiten

- Im Fenster **CREDITS** enthielt die englische Fassung eine Zeile mit
  deutschen Wörtern.
- `THIRD_PARTY_LICENSES.md` führt jetzt auch `lz4` und `pyserial`.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.29.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.29_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.29_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.29.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
