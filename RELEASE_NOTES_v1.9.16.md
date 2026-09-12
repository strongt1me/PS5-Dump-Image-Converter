Ein neuer Knopf unter „Weitere Tools" wandelt ein exFAT-Abbild direkt in ein
installierbares Debug-Paket (.pkg) um – auf Wunsch mit einer selbst gewählten
Ziel-Firmware, und vollständig im Programm.

## Neu: „exFAT → PKG"

Der Weg von einem `.exfat`-Abbild zu einer `.pkg` war bisher zwei getrennte
Schritte. Jetzt gibt es dafür einen eigenen Knopf unter **Weitere Tools**.

Im Fenster wählst du drei Dinge: das **exFAT-Abbild**, einen **Zielordner**
für die fertige `.pkg` und einen **Arbeitsordner** für die Zwischenschritte.
Das Programm entpackt das Abbild, baut daraus ein finalisiertes Debug-Paket
(FIH-Format) und liest es zur Kontrolle wieder ein. Ein Fortschrittsbalken,
eine Statuszeile und ein Protokoll zeigen die ganze Zeit, was läuft;
Abbrechen ist jederzeit möglich.

### Ziel-Firmware

Vor dem Bauen lässt sich eine Firmware angeben – aus der Liste (z.B. `9.00`,
`10.01`) oder von Hand. Das Paket trägt sie dann als benötigte
Systemsoftware, damit eine Konsole mit dieser Firmware es annimmt. Ohne
Angabe bleibt die Firmware des Abbilds unverändert.

Wichtig: Das ändert nur die **Angabe** im Paket. Es rüstet ein Spiel nicht
auf eine ältere Firmware um. Ob ein Titel tatsächlich läuft, hängt weiter an
seinem Programm und seinen Bibliotheken.

### Ganz im Programm

Entpackt wird mit der eingebauten Engine – **kein OSFMount, keine
Administratorrechte**. Gebaut wird mit dem schon mitgelieferten Paketbauer.
Es muss nichts nachinstalliert werden.

Die Kette wurde an einem echten Abbild bis zum fertigen, wieder lesbaren
Paket geprüft. Ob die Konsole ein so gebautes Paket annimmt, hängt wie immer
an ihrer Betriebsart und Firmware.

## Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.16.exe` | Windows 64-bit |
| `SOURCE_FILE_MANIFEST_v1.9.16.sha256` | Prüfsummen der Quelldateien |

Die Programmdatei läuft eigenständig; es muss nichts nachinstalliert werden.
