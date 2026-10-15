Aus jedem Abbildformat ein installierbares Paket, ein neues Lese-Werkzeug für
`.pkg`-Dateien, eine echte Fortschrittsanzeige mit Abbrechen beim Umwandeln,
vier neue Designs – und ein Fix gegen das Einfrieren beim Starten.

## „exFAT → PKG" wird „Abbild → PKG" – alle vier Formate

Der Knopf unter „Weitere Tools" verwandelte bisher nur ein `.exfat`-Abbild in
ein installierbares Debug-Paket. Er heißt jetzt **„Abbild → PKG"** und nimmt
**jedes** Abbildformat des Programms:

- `.exfat` – nativ ausgepackt (MkPFS, ohne Mount, ohne Adminrechte)
- `.ffpfsc` / `.ffpfs` – über die erprobten Auspack-Wege (inkl. Verschachtelung)
- `.ffpkg` – über denselben Weg wie Aufgabe 4 (gepatchtes UFS2Tool, auch > 2 GB)

Danach wird wie gehabt auf Wunsch die Ziel-Firmware in `param.json` gesetzt und
mit dem eingebetteten ProsperoPkg (LibProsperoPkg 2.5) gebaut. An echten
Abbildern in allen vier Formaten geprüft – jedes ergab dasselbe, gültige Paket
(221.816.401 Byte).

## Neu: „PKG lesen"

Ein neues Werkzeug unter „Weitere Tools" liest den **äußeren Container** einer
`.pkg` und zeigt:

- Typ (`Meta` = nur Metadaten, `FullDebug`/`FullRetail` = vollständiges Abbild)
  und die Magic-Kennung (`.CNT` / `.FIH`)
- **Content-ID** samt abgeleiteter **Title-ID** und **Region**
- Größe, Flags, Inhalts-Typ und die **Eintragstabelle** des Pakets

Die eingebettete PFS mit dem eigentlichen Spiel ist verschlüsselt und lässt
sich nicht auflisten – der äußere Rahmen dafür vollständig. Getestet an echten
Paketen.

## Fortschritt und Abbrechen beim Umwandeln

Das Fenster „Abbild → PKG" zeigt beim Auspacken jetzt einen laufenden
Fortschrittsbalken und während des (teils langen) Paketbaus eine sichtbare
Aktivitätsanzeige. Neu ist ein **Abbrechen-Knopf**, der einen laufenden Vorgang
sauber stoppt (Extraktion wie Paketbau). Das Protokoll füllt sich zuverlässig
mit; am Ende steht klar „Fertig – <Größe>" oder „Abgebrochen".

## Vier neue Designs

Unter **DESIGN** stehen jetzt vier eigenständige Farbschemata zur Wahl:

- **Futuristisch** (Neon-Cyan) – leuchtendes Neon-Cyan auf Teal-Schwarz
- **Dunkel** (PS3 Piano Black) – fast schwarz, glänzend, blauer Akzent (Standard)
- **Hell** (PS3 Keramikweiß) – warmes, cremiges Weiß, dunkle Schrift
- **Metallisch** (PS3 Slim) – gebürstetes Anthrazit-Metall, Silber/Stahlblau

„Mittel" entfällt; wer es gewählt hatte, startet mit „Dunkel". Alle vier
Designs bestehen die Kontrast- und Farbschwäche-Prüfungen in allen fünf
Farbschwäche-Einstellungen. Das Auswahlfenster ist größer, damit alle Namen
und Beschreibungen ohne Scrollen passen.

## Behoben: Einfrieren beim Starten

Mit angehaktem **AMPR EMU** oder **BACKPORT** fror das Programm beim
„STARTEN" ein („Keine Rückmeldung"), wenn ein exFAT-Abbild (Aufgabe 3)
oder eine `.ffpkg` (Aufgabe 4, ebenso Aufgabe 6) zu `.ffpfsc` werden sollte –
die vorgesehene Rückfrage erschien nie. Jetzt kommt sie sofort, und **Ja**
erledigt alles in einem Zug: Das Abbild wird entpackt, die gewählten
Bestandteile (AMPR EMU samt Asset-Pack, BACKPORT) werden eingebaut, und danach
wird automatisch wieder `.ffpfsc` gepackt; der vorübergehende Dump-Ordner wird
entfernt. **Nein** beendet den Vorgang, ohne etwas zu schreiben. Auf der
Kommandozeile: `--umhuellt-neu-packen`. Am echten 153-GB-Abbild nachgestellt und
behoben. Dieselbe Ursache
betraf FTP-Wege, die ftpsrv erst an die Konsole schicken wollen (etwa das
Ablegen des WebKit-Installers auf USB).

## Kleinigkeiten

Im Fenster „unjail senden" wurde die Knopfleiste bei sehr kleinem Fenster auf
wenige Pixel zusammengedrückt – sie sitzt jetzt fest am unteren Rand und bleibt
immer voll sichtbar.

In den Untertiteln von „Abbild → PKG" und „PKG bauen" stand vor „FIH"
ein Steuerzeichen, das als leeres Kästchen erschien – jetzt schlicht „(FIH)".

Die Zeile neben dem Fortschrittsbalken („Copy: … | Rest: … | … MB/s | ETA: …")
brach bei 125 % Anzeigeskalierung um. Ihre Breite wird jetzt an der tatsächlichen
Schrift gemessen statt fest auf 520 Pixel gesetzt: Alle gewöhnlichen Zeilen passen
in eine Linie, der Balken ist etwas kürzer und behält seine Länge.

Auf der Kommandozeile kamen `--umhuellt-als-ordner`, `--param-json-reparieren`,
`--param-json-online` und `--ampr-index-trotz-assets` bei gewöhnlichen Aufgaben
nie an und blieben wirkungslos. Jetzt greifen sie wie beschrieben.

## Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.19.exe` | Windows 64-bit |
| `SOURCE_FILE_MANIFEST_v1.9.19.sha256` | Prüfsummen der Quelldateien |

Die Programmdatei läuft eigenständig; es muss nichts nachinstalliert werden.
