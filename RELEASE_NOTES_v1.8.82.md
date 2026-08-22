# PS5 Dump & Image Converter v1.8.82

**22.08.2026**

Diese Ausgabe entfernt die Funktion **PS4 PKG → ffpfsc** vollständig.

## Was verschwindet

| Ort | Umfang |
| --- | --- |
| Hauptprogramm | 1 141 Zeilen: das Fenster, elf Hilfsmethoden, vier Modulfunktionen, drei Konstanten |
| Titelleiste | der Menüeintrag, der das Fenster öffnete |
| Sprachdatei | 65 Schlüssel (`ps4pkg.*` und `titlebar.ps4pkg`) |
| Eingebettetes Werkzeug | `PS4FFPFSC-0.2.8/` — **12 MB, 77 Dateien** |
| Tests | `test_ps4_pkg_converter.py`, `test_ps4_einblendung.py`, ein Test aus `test_fensterlayout.py` |
| Bauspezifikationen | die Bündelung des Werkzeugs in allen drei `.spec`-Dateien |
| Handbuch | Abschnitt 13.8 |

Auch die interne Kommandozeile `--ps4ffpsc` / `--ps4-mkpfs` ist weg, mit der
das Programm sich selbst aufrief, um das Werkzeug anzutreiben.

## Was bleibt

Alles andere. Das Programm wandelt PS5-Abbilder weiterhin in allen bisherigen
Aufgaben um — Dump-Ordner, `.ffpfsc`, `.exfat`, `.ffpkg`, Sammel- und
AIO-Konvertierung, AMPR EMU Manager, Validator. Die eingebettete
MkPFS-Packmaschine bleibt ebenfalls; sie hat mit dem PS4-Werkzeug nichts zu
tun.

**Die EXE schrumpft von 116,3 MB auf 112,1 MB** — 4,2 MB weniger. Nicht die
vollen 12 MB des Ordners: PyInstaller komprimiert die Datenordner im Bündel,
und ein guter Teil davon waren gut komprimierbare Python- und Textdateien.

## Was das für PS4-Spiele bedeutet

Wer aus PS4-PKG-Dateien Abbilder bauen will, braucht dafür jetzt ein anderes
Werkzeug. Die Erkenntnisse aus der Arbeit an dieser Funktion bleiben
gültig und stehen in den Anmerkungen zu v1.8.79 bis v1.8.81 — insbesondere:

* Ein PS4-Titel aus einem Abbild registriert **keine Trophäen**. Das ist
  Sonys Prüfkette, nicht ein Fehler des Abbilds; PS5-Titel aus Abbildern sind
  nicht betroffen.
* Abbilder gehören in die **Wurzel** des USB-Datenträgers, nicht in einen
  Unterordner.

## Aufräumarbeiten am Rande

Ein Blick auf die Zeilenenden: Die drei `.spec`-Dateien haben gemischte
Zeilenenden (in der Windows-Fassung 284 CRLF von 307 Zeilen). Die Ausbauten
wurden deshalb zeilenweise mit dem jeweils eigenen Zeilenende
zusammengesetzt, statt die Dateien durch einen Textdurchlauf zu
vereinheitlichen — sonst stünden 23 Zeilen Rauschen im Unterschied.

## Tests

Die zwei reinen PS4-Testdateien sind entfallen, ein Layouttest ebenfalls, und
zwei weitere Tests wurden auf den verbliebenen Bestand gekürzt.
