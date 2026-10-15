# PS5 Dump & Image Converter v1.9.44

- **Neu:** Die **Bibliothek** ist eine Seite der Ansicht KONSOLE – für den Rechner oder die PS5, mit Holen und Senden, App-Dumper, Firmware-Abgleich, Update-Hinweis und einheitlichem Umbenennen. Der **Koppel-Assistent** führt Schritt für Schritt durch ActRemoteLink.
- **Behoben:** Viele Fehler aus einer vollständigen Durchsicht – „Abbrechen“ greift jetzt überall, das Fenster wartet nicht mehr auf langsame Laufwerke, und die englische Oberfläche ist vollständig übersetzt.
- **Geändert:** Beim Start legt das Programm kein Zertifikat und keine Virenschutz-Ausnahmen mehr an. Neue Payload-Fassungen, unter anderem ShadowMount+ 1.7beta1 und PKG Manager 1.2.4.

## Aufräumen nach älteren Fassungen

Fassungen bis v1.9.43 haben beim Start ein selbst signiertes Zertifikat installiert und Ausnahmen im Windows Defender eingetragen. Wer beides entfernen will, führt in einer PowerShell **als Administrator** aus (Pfade der alten EXE einsetzen):

```powershell
Get-ChildItem Cert:\LocalMachine\Root, Cert:\LocalMachine\TrustedPublisher, Cert:\LocalMachine\My | Where-Object Subject -eq 'CN=PS5 Dump Image Converter' | Remove-Item
Remove-MpPreference -ExclusionPath 'C:\Pfad\zum\Ordner\der\alten\EXE'
Remove-MpPreference -ExclusionProcess 'C:\Pfad\zur\alten\PS5_Dump_Image_Converter.exe'
```

Bei anderen Virenschutzprogrammen die Ausnahme für den Programmordner dort entfernen.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.44.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.44_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.44_linux_x86_64
  ```

- **macOS:** `PS5_Dump_Image_Converter_v1.9.44_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.44_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.
- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.44.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
