# Release-Notizen v1.7.80

## Wichtigste Punkte

- Aufgabe 7 unterstützt jetzt auch `.ffpkg` als Quelle für den fakelib-Workflow.
- Aufgabe 7 erzeugt `ampr_emu.index` jetzt bei Bedarf automatisch für AMPR-Emulations-Builds.
- Vorschau, Infobox und Fortschrittsanzeige wurden in mehreren Aufgabenpfaden robuster und schneller gemacht.
- Die Windows-EXE enthält jetzt saubere Versionsinformationen.
- Der Build nutzt keinen UPX-Packer mehr, um False Positives durch Antivirus und SmartScreen eher zu reduzieren.

## Wichtige Änderungen

- Aufgabe 7 repackt `.ffpkg`-Quellen nach Bearbeitung bewusst als `.ffpfsc`.
- Aufgabe 7 regeneriert `ampr_emu.index` automatisch, sobald `fakelib/libSceAmpr.sprx` als Marker erkannt wird.
- Aufgabe 1 wurde für Neustart nach Abbruch, Progress-Mapping und Kompressions-Logs gehärtet.
- Aufgabe 1 zeigt im laufenden MkPFS-`compress`-Schritt die Größen-/ETA-Zeile jetzt explizit als `Kompr.` an; der Fortschrittsbalken bleibt der Gesamtfortschritt über Scan, Read und Kompression.
- Aufgabe 2 nutzt schnellere reportbasierte Vorschaupfade und eine korrigierte Schrittgeometrie.
- Aufgabe 4 behandelt Schrittgrenzen und Progress-Clamping robuster.
- Der Build fügt der EXE jetzt `FileVersion`, `ProductVersion`, `FileDescription`, `ProductName` und `CompanyName` hinzu.

## Validierung

- Quality Suite: 8/8 PASS
- Build Readiness: 7/7 PASS
- Frischer EXE-Build: erfolgreich
- EXE-Starttest: erfolgreich
- Gezielte Admin-Validierung für Aufgabe 7 mit `.ffpkg`: PASS
- Sichtbarer Rest-/ETA-Nachweis für Aufgabe 7 `.ffpkg` im Hauptlauf: PASS (`_e2e_output_a7_ffpkg_admin_live_20260708_ui_finalproof/e2e_report_a7.json`)

## Build-Artefakt

- Datei: `dist/PS5_Dump_Image_Converter_v1.7.80.exe`
- Größe: 33.08 MB
- SHA-256: `6B31B8236E782CBA2C5ECE4BB9A1232936B00A661308EBC496925B0D41F224A8`
- Signaturstatus: `Nicht signiert`

## Hinweise

- Die EXE fordert Administratorrechte an.
- Für exFAT-bezogene Workflows muss OSFMount installiert und nutzbar sein.
- Ohne Code-Signing-Zertifikat kann Windows SmartScreen oder Antivirus die EXE weiterhin vorsichtig behandeln.

## Bekannte Einschränkungen

- Die EXE ist derzeit nicht digital signiert.
- Aufgabe 7 mit `.ffpkg` benötigt typischerweise Administratorrechte.
- Nicht-erhöhte Einzeltests bestimmter exFAT-/Mount-Pfade können an UAC oder OSFMount scheitern.