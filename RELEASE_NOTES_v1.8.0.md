# PS5 Dump & Image Converter v1.8.0 – Release Notes

## Zweck dieses Releases

Version **v1.8.0** erweitert das Programm um eine breite, recherche-basierte Szene-Werkzeug-Suite – abgeglichen mit realen PS5-Homebrew-Werkzeugen (ps5-exfat-builder, LibProsperoPKG, PS-Multi-Tools u. a.) – bei unveränderter, weiterhin abgesicherter FFPKG-Kernlogik aus v1.7.90. Zusätzlich behebt dieses Release drei reproduzierbare GUI-Abstürze, die ein systematischer Debug-Durchlauf aufdeckte.

## Neue Funktionen

| Bereich | Funktion |
| --- | --- |
| Format | `.ffpfs` (unkomprimiertes Zielformat) bei Aufgabe 1/3/5/6 |
| Performance | Cross-Drive-Staging-Optimierung (vermeidet Lese-/Schreib-Kontention) |
| Performance | Live-Systemtelemetrie (CPU/RAM/Temp-Speicher) während laufender Aufgaben |
| PS5-`.pkg`-Format | PKG-Inspektor (Nur-Lese-Struktur-Viewer) |
| PS5-`.pkg`-Format | PKG-Merger (Split-Package-Wiederzusammenführung) |
| PS5-`.pkg`-Format | FPKG-Builder (strukturell gültiges, unsigniertes Debug-`.pkg` erstellen) |
| Interop | GP5-Projektdatei-Import/Export für externe PKG-Builder |
| Metadaten | Param-/Manifest-Editor (`param.json`/`manifest.json`) |
| Organisation | Bibliothek (Multi-Ordner-Scan, Suche, Cover-Vorschau) |
| Organisation | Dump-Rename (PPSA-Erkennung, Konfidenz-Status, Batch-Umbenennung) |
| Diagnose | Diagnosebericht-Generator (Version/System/Log, geschwärzte Zugangsdaten) |
| Sprache | Deutsch/Englisch-Grundgerüst (Titelleisten-Buttons + Aufgaben-Namen) |
| PS5-Kommunikation | Klog (Kernel-Log-Monitor über TCP) |
| PS5-Kommunikation | ShadowMount+/MicroMount Konfigurationseditor (FTP) |
| PS5-Kommunikation | PS5-Game-Manager (lokal ↔ Konsole Abgleich, FTP) |
| PS5-Kommunikation | DPI-Installer (Direct Package Installer V2 Upload-Client) |
| Analyse | SELF-Inspektor (Nur-Lese-Struktur-Viewer für PS4/PS5-SELF-Dateien) |

Alle neuen Werkzeuge sind über eigene Titelleisten-Buttons erreichbar und lösen keine bestehende Konvertierungslogik (Aufgaben 1–8) ab, sondern ergänzen sie.

## Bewusst nicht umgesetzt (mit Begründung)

Mehrere im Ökosystem-Vergleich identifizierte Funktionen wurden nach Recherche **bewusst nicht** umgesetzt, weil sie entweder automatisierte Exploit-Logik, echte Kopierschutz-Entschlüsselung oder einen unverhältnismäßigen externen Abhängigkeitsaufwand erfordert hätten:

- **Y2JB-Manager**: installiert laut echtem Quellcode ein Paket, das eine YouTube-App-Schwachstelle zum Jailbreak-Auslösen ausnutzt, und patcht System-Updates zur Persistenz – automatisiertes Exploit-Werkzeug.
- **Echte RSA-3072-Signatur / Fake-SELF-Spoofing** im FPKG-Builder: bräuchte proprietäres, nicht beschaffbares Schlüsselmaterial bzw. würde eine Sony-Signatur vortäuschen.
- **SELF-Decrypter** (echte Entschlüsselung): reduziert auf reinen Struktur-Inspektor – echte Entschlüsselung bräuchte Konsolen-Schlüssel aus einem Exploit-Dump.
- **Backports-Tab/Backporter** (Binär-Patching von SELF-Modulen): der sichere Teil (Fakelib, SDK-Versionsfeld) war bereits über Aufgabe 7 und den Param-Editor abgedeckt; der unsichere Teil (echte Entschlüsselung+Neusignierung oder unzuverlässiges Byte-Patching) wurde abgelehnt.
- **Payload-Builder**: konkret mit echtem, frisch installiertem LLVM/Clang 22.1.8 getestet – das PS5-Payload-SDK benötigt ein Sony-/Community-spezifisches `x86_64-sie-ps5`-LLVM-Target, das im offiziellen Mainline-LLVM nicht existiert. Nicht praktikabel umsetzbar.
- **RCO-Dumper**: RCO ist ein PS3-/PSP-/Vita-Format, das die PS5 nicht verwendet – nicht anwendbar auf dieses Projekt.

Details und Recherche-Belege stehen in der projektinternen Backlog-Historie.

## Bugfixes

Ein systematischer Debug-Durchlauf (Syntax-Check, volle Testsuite, headless-Smoke-Test aller Dialoge, projektweite AST-Analyse) deckte drei reproduzierbare Abstürze durch ein wiederkehrendes Tkinter-Muster auf (`padx=(...)`/`pady=(...)`-Tupel im Widget-Konstruktor statt in `.pack()`/`.grid()`):

- Bibliothek-Fenster (Detail-Panel)
- Diagnosebericht-Fenster
- PKG-Merger-Fenster (Protokoll-Bereich)

Alle drei Fenster wurden korrigiert und headless neu verifiziert; eine AST-basierte Prüfung bestätigt, dass keine weiteren Vorkommen dieses Musters in der Datei existieren.

### "Keine Rückmeldung" bei Dump-Rename und Bibliothek

Ein Nutzer-Screenshot zeigte das Dump-Rename-Fenster mit "(Keine Rückmeldung)" im Titel bei 32 gefundenen Dump-Ordnern. Ursache: Die Metadaten-Analyse (Lesen von `param.json`/Cover je Ordner) lief **synchron im UI-Thread**, bevor das Fenster aufgebaut wurde – bei vielen/großen Dumps auf externen oder Netzlaufwerken blockiert das spürbar den Tk-Mainloop. Dieselbe blockierende Schleife fand sich unverändert auch im **Bibliothek**-Fenster. Beide laufen jetzt in einem Hintergrund-Thread (Dump-Rename zeigt währenddessen ein Fortschrittsfenster); end-to-end mit echtem `root.mainloop()` und synthetischen Dump-Ordnern verifiziert. Die EXE dieses Releases wurde mit diesem Fix gebaut.

## Abnahmenachweis

Das projekteigene Release-Test-Gate (`.github/skills/release-test/scripts/run_all_tests.py`) bestand vollständig:

- Syntax-Check: bestanden
- Build-Readiness-Tests: 22 Tests bestanden
- Code-Quality-Suite: 39 Tests bestanden

Zusätzlich bestanden alle 77 über `unittest discover` gefundenen Modultests (inklusive der 6 neuen Testmodule dieses Releases: `test_pkg_reader`, `test_gp5_project`, `test_pkg_merger`, `test_param_manifest`, `test_dump_rename`, `test_i18n`, `test_ini_config`, `test_pkg_writer`, `test_dpi_upload`, `test_self_reader`), sowie die bereits abgesicherte FFPKG-Kernlogik aus v1.7.90 (unverändert, nicht Teil dieses Releases).

## Vollständigkeit des Release

Das vollständige Quellarchiv enthält den gesamten Projektbestand inklusive `.github/`, `MkPFS-0.0.9/`, `helloworld/`, `extract_icon.py`, Changelog, Release Notes und vollständigem Quellhashmanifest (`SOURCE_FILE_MANIFEST_v1.8.0.sha256`). Die Pflichtdateien liegen zusätzlich eigenständig im Releaseordner vor.
