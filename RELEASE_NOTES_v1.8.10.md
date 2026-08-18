# PS5 Dump & Image Converter v1.8.10 – Release Notes

## Zweck dieses Releases

Version **v1.8.10** ist das Ergebnis einer vollständigen Gegenprüfung aller fünf unterstützten Backup-Formate (Dump-Ordner, `.ffpfsc`, `.ffpfs`, `.exfat`, `.ffpkg`) gegen die zugrunde liegende, im Projekt mitgelieferte PFS-/exFAT-Referenzbibliothek (MkPFS-0.0.9) sowie einen externen, unabhängig entwickelten exFAT-Builder. Dabei wurde ein ernster Fehler in Aufgabe 1 (Dump-Ordner → `.ffpfsc`/`.ffpfs`) gefunden und behoben, eine Vollständigkeitsprüfung für `.exfat` ergänzt und `.ffpfs` als Quellformat in allen Aufgaben nachgezogen.

## Fehler 1: Zu tief verschachteltes PFS-Image bei Aufgabe 1

### Symptom

Kein direkt sichtbares Fehlerbild im Programm selbst – die Konvertierung meldete Erfolg. Der Fehler betrifft die innere Struktur der erzeugten `.ffpfsc`/`.ffpfs`-Datei.

### Ursache

Aufgabe 1 baut das Ergebnis in zwei Schritten: zuerst ein rohes, unkomprimiertes inneres PFS-Image direkt aus den Spieldateien, danach den äußeren Container (komprimiert für `.ffpfsc`, unkomprimiert für `.ffpfs`) darum. Dem ersten Schritt fehlte das Flag, das die PFS-Bibliothek anweist, den Ordner direkt als PFS zu packen (`--raw`). Ohne dieses Flag greift der Standardpfad der Bibliothek: Der Ordner wird automatisch in ein zusätzliches, zwangsläufig komprimiertes exFAT-Image gewickelt – unabhängig davon, ob eine unkomprimierte Ausgabe angefordert wurde, und unabhängig von der gewünschten Blockgröße.

Ergebnis: Statt der beabsichtigten zwei Verschachtelungsebenen (äußeres PFS → inneres PFS → Spieldateien) entstanden drei (äußeres PFS → inneres PFS → exFAT → Spieldateien). Eine Quellcode-Anmerkung an anderer Stelle im Programm beschreibt genau dieses Risiko: dass ein zu tief verschachteltes PFS-Image dazu führen kann, dass die PS5 die Metadaten (`param.json`) nicht findet.

### Fix

Das fehlende `--raw`-Flag wird jetzt beim Bau des inneren PFS gesetzt. Dadurch:

- entsteht das innere PFS direkt aus den Spieldateien, ohne exFAT-Zwischenschicht,
- wirkt die Kompressions-Einstellung (`--no-compress`) jetzt tatsächlich auf den inneren Baustein, statt stillschweigend ignoriert zu werden,
- wird die gewählte Blockgröße korrekt angewendet, statt auf einen internen Standardwert zurückzufallen.

### Verifikation

- Die vollständige Pipeline wurde mit einem echten, 191 Dateien umfassenden Spielordner nachgebaut (identischer Aufruf wie im Programm): Schritt 1 erzeugt jetzt nachweislich ein unkomprimiertes PFS ("Compression: disabled", Ausgabegröße nahe der Rohgröße), Schritt 2 baut den äußeren Container darum.
- Das entpackte Ergebnis wurde bis auf die Ebene der Spieldateien zurückverfolgt: Die Verschachtelungstiefe liegt jetzt bei zwei Ebenen (äußeres PFS → inneres PFS → Spieldateien) – derselben Tiefe wie bei einer bekannt funktionierenden Referenzdatei des Nutzers (äußeres PFS → exFAT → Spieldateien).
- **Offene Frage, die nur auf echter Hardware zu klären ist:** Die Referenzdatei nutzt als innere Schicht ein exFAT-Image, der reparierte Programmpfad ein rohes PFS-Image. Beide liegen auf derselben Verschachtelungstiefe, aber ob die PS5/ShadowMountPlus ein inneres rohes PFS genauso zuverlässig liest wie ein inneres exFAT, ist durch reine Code-Analyse nicht abschließend zu bestätigen. Ein Testlauf mit einem über Aufgabe 1 neu erstellten `.ffpfsc` auf echter Hardware wird empfohlen, bevor dieser Punkt als vollständig abgeschlossen gilt.

## Fehler 2: exFAT-Validierung ohne Vollständigkeitsprüfung

### Ursache

`ps5_validator/modules/extfat_validator.py` prüfte bislang nur Boot-Sektor-Struktur (OEM-Name, Signatur, Cluster-Anzahl) und die vollständige Lesbarkeit der Datei per SHA-256 – dieselbe Lücke, die in v1.8.9 bereits bei `.ffpkg` geschlossen wurde. Eine strukturell gültige, aber inhaltlich unvollständige `.exfat`-Datei wäre unbemerkt als gültig durchgegangen.

### Fix

Neue Methode `_verify_exfat_file_count()`: Nach dem Bau eines `.exfat`-Images wird der Verzeichnisbaum über den vendorten, reinen Python-exFAT-Reader (`mkpfs.exfat.ExfatReader`) gelesen und die enthaltene Dateizahl mit der zuvor am Quellordner ermittelten verglichen – rein lesend, ohne Mount, ohne Adminrechte oder zusätzliche Treiber. Weicht die Zahl ab, wird das Image verworfen statt übernommen.

### Verifikation

Der Reader wurde gegen eine bereits vorhandene, echte `.exfat`-Datei getestet (656 MB, aus einem 191-Datei-Quellordner gebaut) und zählte korrekt 191 Dateien.

## Verbesserung 3: `.ffpfs` als Quelle in allen Aufgaben

### Ursache

`.ffpfs` (unkomprimierte Variante von `.ffpfsc`) wird von Aufgabe 1, 3, 5 und 6 als Ausgabe erzeugt, konnte bislang aber nur im Validator (Aufgabe 8) wieder als Quelle ausgewählt werden. Die zugrunde liegende PFS-Bibliothek unterscheidet beim Lesen nicht zwischen `.ffpfsc` und `.ffpfs` (rein inhaltsbasierte Erkennung) – die Blockade war eine reine Lücke in der Quelltyp-Erkennung des Programms, keine technische Notwendigkeit.

### Fix

`.ffpfs` wird jetzt in der Quelltyp-Erkennung, den Dateiauswahl-Dialogen, der Drag-&-Drop-Prüfung und den internen Verarbeitungspfaden von Aufgabe 2, 4, 5, 6 und 7 gleichwertig zu `.ffpfsc` behandelt.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.10** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`

Vollständige Testsuite (77 Tests) bestanden, Syntax-Check erfolgreich.
