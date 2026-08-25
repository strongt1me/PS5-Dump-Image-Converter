# PS5 Dump & Image Converter

![Plattform](https://img.shields.io/badge/Plattform-Windows%20%7C%20Linux%20%7C%20macOS-0078D6)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Version](https://img.shields.io/badge/Version-v1.8.99-blue)
![Tests](https://img.shields.io/badge/Tests-1503%20gr%C3%BCn-brightgreen)

Konvertiert, entpackt, packt und prüft PS5-Dump-Formate – über eine grafische
Oberfläche mit acht klar getrennten Aufgaben. Unterstützt werden Dump-Ordner,
`.ffpfsc`, `.exfat` und echte UFS2-basierte `.ffpkg`-Dateien.

Läuft unter **Windows**, **Linux** und **macOS**. Einzelne Abläufe, die auf
Windows-Werkzeuge angewiesen sind, bleiben Windows vorbehalten – siehe
[Plattformunterschiede](#plattformunterschiede).

> [!IMPORTANT]
> Nur für **eigene, rechtmäßig erworbene** Inhalte. Piraterie und das
> Umgehen von Kopierschutz sind ausdrücklich nicht Zweck dieses Projekts –
> siehe [Haftungsausschluss](#haftungsausschluss).

## Installation

Fertige Programme liegen unter
[**Releases**](https://github.com/strongt1me/PS5-Dump-Image-Converter/releases/latest):

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_vX.Y.Z.exe` |
| Linux | `PS5_Dump_Image_Converter_vX.Y.Z_linux_x86_64` |
| macOS (Apple Silicon) | `..._macos_arm64.dmg` |
| macOS (Intel) | `..._macos_x86_64.dmg` |

Unter Windows genügt ein Doppelklick. Unter Linux muss die Datei einmal
ausführbar gemacht werden (`chmod +x`), unter macOS legt
`Erste Installation.command` aus dem Abbild die App ab und entfernt die
Quarantäne-Markierung.

## Die acht Aufgaben

| Nr. | Aufgabe | Quelle | Ausgabe |
| ---: | --- | --- | --- |
| 1 | Dump-Ordner konvertieren | Dump-Ordner | `.ffpfsc`, `.exfat`, `.ffpkg` |
| 2 | FFPFSC konvertieren | `.ffpfsc` | Dump-Ordner, `.exfat`, `.ffpkg` |
| 3 | exFAT konvertieren | `.exfat` | Dump-Ordner, `.ffpfsc`, `.ffpkg` |
| 4 | FFPKG konvertieren | `.ffpkg` | Dump-Ordner, `.ffpfsc`, `.exfat` |
| 5 | Sammelkonvertierung | mehrere Container | gemeinsames Zielformat |
| 6 | Universal-Export | Ordner oder Container | passendes Zielformat |
| 7 | AMPR EMU Manager | Ordner oder Container | Auswahlfenster: alte oder neue ShadowMount+-Methode (automatisch, je mit Anleitung) oder Einbau ins Backup – Ablage wählbar: pro Spiel, global, Emulatoren |
| 8 | Dump Validator | Ordner oder Container | Integritätsbericht |

Angeboten werden nur Zielformate, die zur erkannten Quelle passen.

## Dokumentation

Das **[Benutzerhandbuch](BENUTZERHANDBUCH.html)** erklärt die Bedienung in
einfacher Sprache – alle acht Aufgaben, die Werkzeugleiste, typische Fehler
und die Besonderheiten unter Linux und macOS. Es liegt auch als
[PDF](BENUTZERHANDBUCH.pdf) (30 Seiten) bei.

Was sich je Version geändert hat, steht im [Changelog](CHANGELOG.md).

## Voraussetzungen

* **Windows 10/11**, eine aktuelle Linux-Distribution oder **macOS 12+**
* Genug freier Speicherplatz für Quelle, Zwischenstand und Ausgabe
* **Windows:** Administratorrechte für Mount- und UFS2-Abläufe,
  [OSFMount](https://www.osforensics.com/tools/mount-disk-images.html) für
  exFAT-Mounts
* **Aus dem Quelltext:** Python 3.10+ und `pip`

## Kommandozeile

Jede Aufgabe läuft auch ohne Fenster – über dieselbe geprüfte Ablauflogik wie
die Oberfläche:

```bash
python PS5ImageConverter_Pro_FINAL_revised.py --cli --task 1 \
  --source "D:\Dumps\Spiel" --dest "D:\Ausgabe" --format ffpkg --yes
```

| Option | Bedeutung |
| --- | --- |
| `--cli` | aktiviert den Kommandozeilenmodus (erforderlich) |
| `--task N` | Aufgabe 1–8 |
| `--source PFAD` | Quellpfad; mehrere nur bei Aufgabe 5 |
| `--dest PFAD` | Zielordner (entfällt bei Aufgabe 8) |
| `--format …` | `folder`, `ffpfsc`, `ffpfs`, `exfat`, `ffpkg` |
| `--temp PFAD` | Arbeitsordner überschreiben |
| `--yes` | Rückfragen automatisch bestätigen |
| `--quiet` | Protokoll nicht auf stdout spiegeln |
| `--shutdown-on-success` | nach Erfolg herunterfahren |

Rückgabewerte: `0` Erfolg · `1` Fehler oder Abbruch · `2` ungültige Argumente ·
`3` fehlende Administratorrechte.

> Unter Windows fordert `--cli` **keine** Rechte an – ein neu gestarteter
> Prozess wäre abgekoppelt, seine Ausgabe erreichte den Aufrufer nie. Starten
> Sie die Eingabeaufforderung deshalb selbst als Administrator.

### Umgebungsprüfung

Läuft etwas nicht, obwohl es anderswo läuft, klappert `--doktor` die häufigen
Ursachen ab und liefert ein Ergebnis, das sich in eine Fehlermeldung kopieren
lässt – ohne Netzzugriff und ohne Zugangsdaten:

```bash
python PS5ImageConverter_Pro_FINAL_revised.py --doktor "E:\Temp" "E:\Ziel"
```

Beide Ordnerangaben sind freiwillig. Geprüft werden unter anderem
abgeschaltete lange Pfade, das Dateisystem der Ordner (auf FAT32 endet jede
Datei bei 4 GB), Schreibrecht und freier Platz, widersprüchliche Paketstände,
ob sich die mitgelieferten Programme überhaupt starten lassen, und ob die
Einstellungsdatei lesbar ist.

Rückgabewerte: `0` nichts zu beanstanden · `1` mindestens ein echter Fehler.
Dieselben Angaben stehen im Fenster **DIAGNOSE** im Abschnitt *Doktor*.

> Die **fertige EXE** verlangt grundsätzlich Administratorrechte – das steht in
> ihrem Manifest und gilt für jeden Aufruf, auch für `--doktor`. Öffnen Sie die
> Eingabeaufforderung deshalb selbst als Administrator. Aus dem Quelltext
> heraus (`python …`) läuft die Prüfung ohne erhöhte Rechte.

## Selbst bauen

```powershell
# Windows
.\Build_EXE.ps1
```

```bash
# Linux
chmod +x Build_Linux.sh && ./Build_Linux.sh

# macOS (--dmg erzeugt zusätzlich das Abbild)
chmod +x Build_macOS.sh && ./Build_macOS.sh --dmg
```

Die Testreihe läuft mit:

```bash
python -m unittest discover -s . -p "test_*.py"
```

## Plattformunterschiede

Oberfläche, alle acht Aufgaben, Kommandozeile und die Übertragung zur PS5
arbeiten überall gleich. Unterschiede gibt es hier:

| Bereich | Linux und macOS |
| --- | --- |
| `.ffpkg` lesen und bauen | **Nicht verfügbar** – UFS2Tool und der Dokan-Treiber sind Windows-Software. Das Programm sagt das beim Start einer solchen Aufgabe. |
| OSFMount-Ersatzwege | Nicht verfügbar; die nativen MkPFS-/exFAT-Wege sind vollständig vorhanden. |
| Erhöhte Rechte | Nicht nötig. |
| Einstellungen | `~/.config/PS5ImageConverterPro/` bzw. `~/Library/Application Support/PS5ImageConverterPro/` |
| Automatische Installation von Fremdwerkzeugen | Nur Windows; FileZilla wird sonst im `PATH` gefunden. |

## Haftungsausschluss

Dieses Projekt dient dem **Sichern und Verwalten von Inhalten, die Sie
rechtmäßig erworben haben**, sowie Bildungs- und Forschungszwecken.

* Verwenden Sie es **ausschließlich** mit Software, die Ihnen gehört.
* Das Umgehen technischer Schutzmaßnahmen, das Beschaffen, Verbreiten oder
  Öffentlich-Zugänglichmachen urheberrechtlich geschützter Inhalte ist
  **nicht** Zweck dieses Projekts und wird nicht unterstützt.
* In vielen Ländern ist bereits das Umgehen eines Kopierschutzes verboten –
  auch bei eigenen Datenträgern. **Prüfen Sie die Rechtslage in Ihrem Land.**
* Die Nutzung erfolgt auf **eigene Verantwortung und eigenes Risiko**. Die
  Autoren übernehmen keine Haftung für Schäden, Datenverlust, defekte
  Geräte oder rechtliche Folgen.
* Veränderungen an einer Spielkonsole können deren Garantie erlöschen lassen
  und sie unbrauchbar machen.

Dieses Projekt steht in **keiner Verbindung zu Sony Interactive Entertainment**
und wird von dort weder unterstützt noch geprüft. Alle Marken gehören ihren
jeweiligen Inhabern.

Sichern Sie Originaldateien vor jeder Bearbeitung separat.

## Lizenz

Die Lizenzen der mitgelieferten Fremdkomponenten stehen in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) und sind im Fenster
**CREDITS** direkt aufrufbar. Einzelne eingebettete Komponenten haben eigene
Bedingungen – vor einer Weiterverteilung bitte prüfen.


## Credits

* **Phoenixx1202 / PSBrew** – [MkPFS](https://github.com/PSBrew/MkPFS)
* **SvenGDK und Mitwirkende** – [UFS2Tool](https://github.com/SvenGDK/UFS2Tool)
* **PassMark Software** – OSFMount
* **Dokan-Projekt** – Windows-Dateisystemtreiber
* **PyInstaller-Projekt** – Programmbündelung

Die Funktion **BACKPORT** setzt auf Verfahren auf, die in der Szene
entwickelt und veröffentlicht wurden.
