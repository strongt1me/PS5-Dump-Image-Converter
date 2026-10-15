# PS5 Dump & Image Converter v1.9.56

- **Neu:** Aufgabe 1 baut AMPR EMU (auch als Asset-Pack), PlayGo oder BACKPORT auf Wunsch in einen Dump-Ordner ein – vorher fragt das Programm, ob im Original oder in einer Sicherung eingebaut wird.
- **Neu:** „Konsole & Payloads“ kennt acht weitere Dienste (CheatRunner, App Dumper, Game Compressor, SMPlusGui, aria2, zftpd, GDB-Server, ps5debug-NG); dazu liegen 19 weitere Payloads bei, und ShadowMount+ (1.7beta3), CheatRunner, ps5upload, zftpd und WebKit Autoloader sind aktualisiert. Das Fenster des WebKit Autoloaders nennt die mitgelieferte Fassung.
- **Geändert:** „PKG BAUEN“ ist entfallen; „PKG lesen“ heißt jetzt „PS4 & PS5 PKG lesen“, „PKG entpacken“ heißt „PS4 PKG → Dump Ordner“. Der AMPR-Mitschnitt-Assistent prüft vorab ShadowMount+ auf der Konsole und stellt nach dem Lauf alles zurück. Der Diagnosebericht meldet ein hochgerechnetes Hintergrundbild nur noch, wenn man die Hochrechnung sieht.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.56.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.56_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.56_linux_x86_64
  ```

- **macOS:** `PS5_Dump_Image_Converter_v1.9.56_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.56_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.
- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.56.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
