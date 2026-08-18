# PS5 Dump & Image Converter v1.8.50 – Release Notes

## Zweck dieses Releases

Die dritte Plattform. Nach Windows und Linux gibt es die Anwendung jetzt auch für macOS – als eigenes Programmbündel, nicht als notdürftig portierte Programmdatei.

---

## Ein Bündel, keine Einzeldatei

Unter Linux ist das Ergebnis eine einzelne Datei, die man startet. Auf einem Mac wäre das ein Fremdkörper: keine Zuordnung im Dock, kein Name in der Menüleiste, kein Weg, dem System etwas über die Darstellung mitzuteilen. Deshalb entsteht dort ein **Programmbündel**:

```text
dist/PS5 Dump & Image Converter.app
```

Der Name trägt bewusst **keine** Version. Im Programme-Ordner soll über Updates hinweg derselbe Eintrag stehen, damit eine neue Fassung die alte ersetzt, statt sich danebenzulegen. Die Versionsnummer steht in der Info.plist und im Zwischenordner unter `dist/`.

Drei Einträge in der Info.plist entscheiden darüber, wie das Fenster aussieht:

| Eintrag | Ohne ihn |
| --- | --- |
| `NSHighResolutionCapable` | Das Fenster wird aus einem einfach aufgelösten Puffer auf doppelte Größe gezogen – auf jedem Retina-Bildschirm sichtbar unscharf |
| `NSRequiresAquaSystemAppearance: false` | macOS zwingt das Fenster ins helle Aqua-Aussehen; die hellen Systemleisten stoßen sich mit dem dunklen Design |
| `CFBundleShortVersionString` | Der Finder zeigt gar keine Version an – das Feld erlaubt nur Ziffern und Punkte, das führende `v` aus `APP_VERSION` muss weg |

---

## Was neu dazugekommen ist

| Datei | Aufgabe |
| --- | --- |
| `Build_macOS.sh` | Baut das Bündel; `--dmg` erzeugt zusätzlich ein Abbild zum Weitergeben |
| `Install_macOS.sh` | Legt es nach `/Applications`, ersatzweise `~/Applications`; `--entfernen` nimmt es zurück |
| `PS5ImageConverter_Pro_macos.spec` | `COLLECT` + `BUNDLE` statt Onefile, mit Info.plist |
| `extract_icon_icns.py` | Erzeugt `app_icon.icns` aus `app_icon.ico` |
| `test_macos_fassung.py` | 39 Prüfungen, laufen auf jedem System |

`extract_icon_icns.py` kommt bewusst **ohne Apples `iconutil`** aus – Pillow schreibt das Format in reinem Python. So lässt sich das Symbol auch auf dem Windows-Rechner erzeugen, auf dem der übrige Quelltext gepflegt wird. Die Kacheln von 32 bis 1024 Punkten werden einzeln mit LANCZOS gerechnet; ohne das nimmt Pillow für jede sein eigenes, schlechteres Verfahren, was besonders bei 512 und 1024 auffällt.

---

## Vier Entscheidungen mit Begründung

**Die Signatur ist Pflicht, nicht Kür.** Auf Apple Silicon verweigert das System jede unsignierte Programmdatei den Start. Das Bauskript setzt deshalb zum Schluss eine Ad-hoc-Signatur über das fertige Bündel. Die Reihenfolge ist dabei entscheidend: erst `xattr -cr`, dann `codesign`. Umgekehrt räumt `xattr` genau die Signaturen wieder ab, die `codesign` kurz zuvor in den erweiterten Attributen mitgelieferter Dateien hinterlegt hat.

**Kein `argv_emulation`.** Die Emulation fängt das Apple-Event „öffne Dokument" mit einer eigenen Ereignisschleife ab, bevor Tk seine eigene startet – das Fenster bliebe bis zum ersten Klick taub. Aus demselben Grund meldet das Bündel bewusst keine Dateizuordnung an: Eine Zuordnung, die dann nichts tut, wäre schlechter als keine.

**Apples `/usr/bin/python3` wird abgelehnt.** Ihm fehlt ein brauchbares Tcl/Tk. Das Bauskript sagt das vorab und nennt den Ausweg (`python.org` oder `brew install python-tk`), statt den Bau erst spät scheitern zu lassen. Ebenso verlangt es Tk 8.6 oder neuer: Das systemeigene Tk 8.5 zeichnet Rahmen falsch, kennt kein dunkles Erscheinungsbild und stürzt bei mehreren Fenstern ab.

**Die Skripte kommen ohne GNU-Erweiterungen aus.** macOS liefert bis heute bash 3.2, und dort meldet `"$@"` zusammen mit `set -u` einen Fehler, sobald das Skript ohne Argumente aufgerufen wird – also im Normalfall. Argumente werden deshalb über `while [ $# -gt 0 ]` abgeklappert. `find -printf` und `readlink -f` stehen zwar im Linux-Skript, gibt es in den BSD-Fassungen aber nicht; ein Test hält fest, dass beides nicht mitkopiert wurde.

---

## Was auf dem Mac nicht zur Verfügung steht

Dieselben zwei Wege wie unter Linux, aus demselben Grund: `.ffpkg` lesen und bauen (UFS2Tool und Dokan sind reine Windows-Software) sowie die Ersatzwege über OSFMount. Diese Stellen waren bereits abgeriegelt; neu ist, dass die Meldung jetzt das laufende System beim Namen nennt:

> `… gibt es nur unter Windows. Unter macOS steht dieser Weg nicht zur Verfügung.`

Alle übrigen Aufgaben – Dump-Ordner, `.ffpfsc`, `.ffpfs` und `.exFAT` in jeder Richtung, Sammelkonvertierung, AMPR EMU Manager, Validator, Kommandozeilenmodus, Übertragung zur PS5 – stehen vollständig zur Verfügung.

---

## Schriftwahl ohne fontconfig

Die Oberfläche ist auf *Segoe UI* ausgelegt; die Abstände im Fensteraufbau sind auf deren Maße gerechnet. Unter Linux fragt die Plattformschicht dafür `fc-match`. Auf einem Mac gibt es das nicht, und `system_profiler SPFontsDataType` braucht mehrere Sekunden – zu lang für eine Abfrage, die schon beim Import läuft, weil die Schriftnamen in Vorgabewerten von Funktionssignaturen stehen.

Stattdessen wird in den Schriftordnern des Systems nach den Dateinamen gesehen: `~/Library/Fonts`, `/Library/Fonts`, `/Library/Fonts/Microsoft`, `/System/Library/Fonts` und `/System/Library/Fonts/Supplemental`. Wer Microsoft Office installiert hat, bekommt damit exakt das Windows-Schriftbild; sonst greift *SF Pro Text*, *Helvetica Neue* oder *Lucida Grande*, für Festbreite *SF Mono*, *Menlo* oder *Monaco*.

---

## Tests

**39 neue Prüfungen in `test_macos_fassung.py`**, dazu die vollständige Quality Suite (14/14) und die betroffenen GUI-Testdateien einzeln (17, 11 und 28 Prüfungen, alle grün).

Der interessante Teil ist, wie ohne Mac geprüft wird:

| Prüfung | Wie |
| --- | --- |
| Plattformschicht | Das Modul wird ein zweites Mal geladen, mit `sys.platform = "darwin"` – über `spec_from_file_location`, damit das umgebogene Modul nicht in `sys.modules` landet und spätere Tests ansteckt |
| Bauvorschrift | Die `.spec` wird nicht nur geparst, sondern mit Attrappen statt PyInstaller **ausgeführt**; danach lässt sich jeder eingebettete Pfad gegen das Dateisystem halten |
| Gleichstand mit Linux | Die versteckten Importe beider `.spec`-Dateien müssen deckungsgleich sein – laufen sie auseinander, fällt ein Modul sonst erst zur Laufzeit aus, und zwar nur auf einem der beiden Systeme |
| Skripte | LF-Zeilenenden (ein CRLF quittiert macOS mit `bad interpreter: … bash^M`), Shell-Syntax, keine GNU-only-Schalter, `xattr` vor `codesign` |

Dieselben 39 Prüfungen laufen inzwischen auch auf echtem macOS – siehe unten.

---

## Auf echter Apple-Hardware bestätigt

Für die Entwicklung stand kein Mac zur Verfügung. Diese Lücke schließt der Workflow `.github/workflows/macos-buendel.yml`: Er baut das Bündel auf **beiden** Architekturen und prüft dort, was sich statisch nicht beantworten lässt.

| | Apple Silicon | Intel |
| --- | --- | --- |
| Läufer | `macos-14`, macOS 14.8.7 | `macos-15-intel`, macOS 15.7.7 |
| Bauzeit | 0:56 | 2:41 |
| Tcl/Tk | 8.6 | 8.6 |
| Bündel | 158 MB | 155 MB |
| Abbild | 102 MB | 102 MB |

Was dabei belegt ist:

- **PyInstaller findet alle Räder** in der jeweiligen Architektur – Pillow, cryptography, zstandard, zlib-ng.
- **Die Signatur hält.** `codesign --verify --deep --strict` meldet auf beiden `valid on disk` und `satisfies its Designated Requirement`, die Kennung lautet `Signature=adhoc`.
- **Das gebaute Programm startet.** Der Aufruf `--cli --help` aus `Contents/MacOS/` liefert die Hilfe – er lädt denselben Interpreter, dieselben Bibliotheken und dieselben eingebetteten Daten wie der Fensterbetrieb.
- **Die 39 Tests laufen auf echtem macOS**, nicht mehr nur gegen ein gemocktes `sys.platform`.
- **Die Schriftwahl greift.** Ohne Segoe UI auf einem nackten Läufer fällt sie auf *Helvetica Neue* und *Menlo* zurück – gefunden allein über die Schriftordner, ohne fontconfig.
- **Der Einstellungsordner sitzt richtig:** `~/Library/Application Support/PS5ImageConverterPro`.
- **Die Windows-Sperren melden das richtige System:** „UFS2Tool gibt es nur unter Windows … Unter macOS steht dieser Weg nicht zur Verfügung."

### Was weiterhin offen ist

Zwei Dinge lassen sich auf einem CI-Läufer nicht beurteilen, weil er keine angemeldete Fenstersitzung hat:

1. wie das dunkle Design im Aqua-Rahmen tatsächlich wirkt,
2. ob Drag & Drop über `tkinterdnd2` greift.

Beides braucht einen Mac, an dem jemand sitzt.

**Zur Wahl des Intel-Läufers:** `macos-13` steht auf der Hardware, die GitHub abbaut. Ein Job wartete dort 51 Minuten, ohne überhaupt zu starten, während derselbe Bau auf Apple Silicon nach 65 Sekunden fertig war. Auf `macos-15-intel` lief er sofort an.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.50.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.50_linux_x86_64` | Linux x86-64 (auf dem Zielsystem zu bauen) |
| `dist/PS5_Dump_Image_Converter_v1.8.50_macos_arm64.dmg` | macOS, Apple Silicon – aus dem Workflow |
| `dist/PS5_Dump_Image_Converter_v1.8.50_macos_x86_64.dmg` | macOS, Intel – aus dem Workflow |
| `SOURCE_FILE_MANIFEST_v1.8.50.sha256` | Prüfsummen aller Quelldateien |

Das Auslieferungsbündel nimmt ein vorhandenes macOS-Abbild (`.dmg`) jetzt mit auf – das `.app` selbst ist ein Ordner und verlöre beim Weitergeben über Windows Rechte und erweiterte Attribute, und mit ihnen seine Signatur.
