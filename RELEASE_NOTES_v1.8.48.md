# PS5 Dump & Image Converter v1.8.48 – Release Notes

## Zweck dieses Releases

Vier Funde aus einem Praxistest, jeder mit einer nachgemessenen Ursache. Drei davon waren dem Programm von außen nicht anzusehen: Ein zurückportiertes Backup sah wie ein unverändertes aus, die Firmware-Anzeige log bei jedem dritten Spiel, und der Fortschritt beim `.ffpkg`-Bau stand über die Hälfte der Laufzeit still.

---

## 1. Ein zurückportiertes Backup ist jetzt erkennbar

Ein Backport schreibt die Firmware-Kennung ausschließlich in die **ELF-Kopfdaten** von `eboot.bin` und den `.prx`-Dateien. Die `param.json` bleibt unangetastet – so macht es auch der `ps5-exfat-builder 4.0.2`, dessen `_abp_patch_file` nur ELF- und SELF-Dateien anfasst. Weil das Spiel-Info-Fenster ausschließlich die `param.json` liest, war einem zurückportierten Dump nichts anzusehen.

Neu ist die Zeile **SDK (eboot.bin)**:

| Dump | Anzeige |
| --- | --- |
| Teardown, Original | `9.00` |
| Teardown, zurückportiert | `7.00 (zurückportiert – param.json nennt 9.00)` |
| Terminator 2D | `10.00` |

Bei Container-Quellen bleibt die Zeile leer, statt etwas zu behaupten, das nicht gelesen wurde.

### Warum die Konsole dabei nicht hilft

ShadowMount+ 1.7alpha6 meldet zwar „Spiel backportiert", prüft dafür aber **keinen SDK-Wert**. Sein Kriterium steht in der eigenen `config.ini`:

> `mount app0/fakelib2 when present, otherwise app0/fakelib, into common/lib`

Gemeldet wird also, dass ein Bibliotheksordner eingehängt wurde. Im Protokoll einer Testkonsole löste ein **AMPR-EMU-Paket** dieselbe Meldung aus, obwohl es nicht zurückportiert war – es hat nur einen `fakelib`-Ordner. Umgekehrt blieb ein echter Backport ohne Ersatzbibliotheken unerwähnt.

---

## 2. REQUIRED FW war bei 13 von 32 Spielen falsch

Die Firmware steht in der `param.json` als BCD: Die Hex-**Zeichen** sind die gedruckten Ziffern, `0x1270…` heißt 12.70. Beim Einlesen entfernte die Zeichenklasse aber nur das `x` des Präfixes `0x` – die führende `0` blieb stehen und verschob alles um eine Stelle:

| Spiel | vorher | jetzt |
| --- | --- | --- |
| Teardown | 01.00.10.00 | **10.01.00.00** |
| Mafia The Old Country | 01.20.00.00 | **12.00.00.00** |
| Terminator 2D | 01.12.00.00 | **11.20.00.00** |

Eine Rotation bei führenden Nullen glich das aus – aber nur bei einstelliger Hauptversion. Betroffen war jedes Spiel mit zweistelliger. Gegen 32 echte Dumps geprüft: **0 Abweichungen**.

---

## 3. `fakelib` oder `fakelib2` – wählbar, und für beide Funktionen gemeinsam

ShadowMount+ hängt nur **einen** der beiden Ordner ein und bevorzugt `fakelib2`. Die Wahl steht jetzt im **BACKPORT**-Fenster und im **AMPR EMU Manager** – beide schreiben denselben gespeicherten Wert, und es gibt genau einen Leser. Wer im AMPR-Fenster umstellt, stellt den Backport mit um.

Das ist keine Bequemlichkeit: Lägen Backport-Bibliotheken in `fakelib2` und AMPR in `fakelib`, würde AMPR stillschweigend ignoriert. Existieren nach einem Lauf beide Ordner, warnt das Programm ausdrücklich.

Zwölf vorher festverdrahtete `"fakelib"`-Stellen im AMPR-Manager sind umgestellt, samt FTP-Pfaden und Hot-Swap. Ein unsinniger Wert fällt auf `fakelib` zurück – ein Tippfehler legte sonst einen Ordner an, den die Konsole nie einhängt. Die Vorgabe bleibt `fakelib`.

---

## 4. Der Fortschritt beim `.ffpkg`-Bau stand still

Gemessen an einem 743-MB-Paket, zehn Messungen je Sekunde auf Innenwert, Balken und Prozenttext:

| | vorher | jetzt |
| --- | --- | --- |
| Schritt 3 beginnt bei | **98,0 %** | **56,15 %** |
| längster Stillstand | **49,3 s** bei 98 % | **10,1 s** bei 5 % |
| verschiedene Balkenwerte | 65 | **199** |

Der UFS2Tool-Lauf meldete seinen Fortschritt über die **ganze** Spanne (5 bis 98) und war damit am Ziel, bevor Schritt 3 überhaupt begann – und genau der ist der langsame: Strukturprüfung, Dateizahl per Mount, zwei SHA-256-Durchgänge und die Übertragung. Er meldet jetzt nur bis zur Grenze von Schritt 2; Kopie und Prüfsummen melden ihre Bytes.

Ein erster Versuch griff daneben: Die Änderung der Schrittgewichte allein wirkte nicht, weil der Wert aus einem Ereignis mit eigener Spanne kommt. Der verbleibende Stillstand von 10 s ist der Anlauf von `newfs`/`makefs`, bevor die erste Dateizahl gemeldet wird.

---

## Weitere Änderungen

- **Neue Vorgabe-Hintergrundbilder**: `bg_19_ray-burst.png` und `sidebar_20_glass-panels.png`. Wer bereits ein Bild gewählt hat, behält es; „kein Bild" bleibt „kein Bild".
- **Designwechsel erfasst vier weitere Widget-Gruppen**: Titelleisten-Knöpfe, die abgerundeten Aufgabenknöpfe, die beiden Fußknöpfe der Seitenleiste und beide Klappmenüs. Im hellen Design lag der Kontrast eines Fußknopfs bei **1,19** – praktisch unlesbar.
- **Kontextmenü übersetzt**: „Vollbild", „Verkleinern / Zentrieren" und „Beenden" standen fest auf Deutsch im Quelltext.
- **Hinweis am Worker-Feld**: Ein Tooltip nennt die tatsächliche Wirkung der eingestellten Zahl – wie viele Worker beim Packen entstehen und wie viele Threads der Validator nutzt.

---

## Tests

**47 Testdateien grün.** Neu abgesichert: die BCD-Lesung mit ein- und zweistelliger Hauptversion, die Ordnerwahl samt Rückfall bei unsinnigen Werten, die Kollisionswarnung, die Zwischenmarken im `.ffpkg`-Schritt 3 und die Vorgabebilder.

Ein Hinweis zur Prüftiefe: `test_werkzeugmenue.py` hatte `unittest.main()` mitten in der Datei – alles darunter lief nie mit, darunter eine vollständige Klasse mit drei Tests. Der Einstiegspunkt steht jetzt am Ende.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.48.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.48.sha256` | Prüfsummen aller Quelldateien |
