Diese Fassung bringt keine neuen Funktionen. Sie ist das Ergebnis einer
Durchsicht von **57 offenen Punkten** aus einer Befundliste vom 04.09. — elf
davon waren längst erledigt, 41 wirklich noch da. **Sieben weitere Fehler**
kamen dabei heraus, die in der Liste gar nicht standen.

## AMPR EMU und BACKPORT wurden auf drei Wegen übergangen

Der schwerste Fund, und er kam aus einer Frage: *Wird beim Weg `.exFAT` →
`.ffpfsc` entpackt?* Die Antwort ist nein — das Abbild wird als Ganzes
eingehüllt. Beim Nachsehen fiel auf, dass dabei auch die Integrationskästchen
übergangen werden.

Gemessen wurde jeder Weg zweimal, einmal ohne und einmal mit gesetzten
Kästchen. Verglichen wurden die Protokollspuren und die Dateizahl:

| Weg | ohne | mit | greift |
| --- | --- | --- | --- |
| `.exFAT` → `.ffpfsc` | keine Spur | keine Spur | **nein** |
| `.ffpkg` → `.ffpfsc` | keine Spur | keine Spur | **nein** |
| `.ffpkg` → Dump-Ordner | 191 Dateien | 191 Dateien | **nein** |
| `.exFAT` → Dump-Ordner | 191 Dateien | **200 Dateien** | ja |
| `.ffpfsc` → `.ffpfs` | 656.474.112 B | **657.981.440 B** | ja |

Die letzten beiden Zeilen sind die Gegenprobe. Ohne sie wüsste man nicht, ob
die Messung überhaupt etwas sieht.

Zwei verschiedene Ursachen, deshalb zwei verschiedene Behebungen:

**`.ffpkg` → Dump-Ordner konnte einbauen und tat es nur nicht.** Das
Gegenstück für die `.exFAT` macht es seit jeher. Nachgeholt — nachgemessen
sind es jetzt ebenfalls 200 Dateien.

**Die beiden `.ffpfsc`-Wege können es nicht.** Sie hüllen das Abbild als eine
einzige Datei in den Container und öffnen seinen Inhalt nie. Ein Umweg über
den Dump-Ordner ergäbe eine andere Bauform der Ausgabe — das lässt sich ohne
Konsolentest nicht verantworten. Das Programm **warnt jetzt vor dem Start**
und nennt den Umweg, statt ein Backup ohne AMPR EMU zu liefern, das man für
eines mit hält.

## Vier zusammengedrückte Knopfreihen

Bisher hatte jedes Fenster hier seine eigene Prüfung — und deshalb fiel nicht
auf, dass weitere dieselbe Falle hatten. Eine neue Prüfung zieht **alle
zwanzig** Werkzeugfenster auf ihre kleinste Größe und misst die Knöpfe nach:

| Fenster | war | ist |
| --- | --- | --- |
| Param-/Manifest-Editor | 12 px | 42 px |
| SELF-Inspektor | 10 px | 42 px |
| Dump Rename | 8 px | 42 px |
| KLOG (Breite) | 115 px | 135 px |

Bei den ersten drei half nur die umgekehrte Packreihenfolge; ein nachträgliches
`side="bottom"` reicht nicht — auch das ist nachgemessen.

Ein fünfter Fund trat **nur auf Deutsch** auf: „Auf PS5 schreiben…" bekam im
ShadowMount+- und MicroMount-Editor 158 statt der benötigten 242 px. Die
englischen Beschriftungen sind kürzer, in der englischen Fassung passte es —
deshalb ist es nie jemandem aufgefallen. Die Prüfung legt die Sprache jetzt
fest, sonst findet sie so etwas mal und mal nicht.

## Wenn etwas misslingt, sagt es das Programm

Der häufigste Fund war immer dasselbe Muster: Ein Aufruf scheitert, die
Oberfläche geht wortlos in den Ruhezustand, und der Knopf sieht kaputt aus.

- **KLOG** deutete jeden Verbindungsabbruch als „Datei nicht vorhanden" — und
  bot dann an, den Payload in die Stickwurzel zu legen, obwohl er die Frage
  gar nicht stellen konnte. Jetzt heißt nur eine Absage der Konsole „gibt es
  nicht"; alles andere wird als Fehler behandelt.
- **Die Bibliothek** überging unlesbare und verschwundene Suchordner
  stillschweigend. Wer eine externe Platte abgezogen hatte, sah nur eine
  kürzere Trefferliste ohne Grund.
- **FileZilla** verwarf eine abgelehnte Dateiauswahl kommentarlos, und eine
  misslungene Installation stand nur im Protokoll.
- **Der Autoloader** kehrte bei einem leeren Ordner wortlos zurück. Und sein
  Arbeitsfaden meldete an ein Fenster, das man inzwischen geschlossen haben
  kann — dann endete er mitten in der Übertragung.
- **Der WebKit-USB-Weg** zeigte Fehler nur im Meldungsfenster. Nach dem
  Wegklicken waren sie verloren, auch für den Diagnosebericht.

## Kleineres, das trotzdem störte

- Der **Param-/Manifest-Editor** riet den Dokumenttyp am Dateinamen. Wer eine
  Manifestdatei `param.json` nannte, bekam die falschen Felder und beim
  Speichern das falsche Format. Er entscheidet jetzt am Inhalt — und prüft
  nach dem Speichern, was er geschrieben hat. Eine `.json`, die zwar gültig
  ist, an der Wurzel aber kein Objekt trägt, ließ ihn bisher abstürzen.
- **Dump Rename** hielt `CUSA00000` für eine PS5-Kennung und bot PS4-Dumps
  Namensvorschläge an, die es gar nicht anbieten will. Es lehnte außerdem eine
  reine Groß-/Kleinschreibungsänderung mit „existiert bereits" ab, und nach
  dem Umbenennen zeigte das Quellfeld weiter auf den alten Namen. Ohne
  Versionsangabe standen zwei gleiche Vorschläge da, beide markiert.
- Der **WebKit-Host** lief unter Linux und macOS unsichtbar — die Adresse, die
  er beim Start nennt, sah niemand. Seine Ausgabe geht jetzt in eine Datei.
  Und er meldete „gestartet", auch wenn er sofort wieder starb.
- Der **AMPR-Index-Builder** schrieb aus einem leeren Ordner einen Index mit
  null Einträgen — über eine womöglich brauchbare Datei am selben Ort. Er nahm
  außerdem alles auf, was kein Verzeichnis ist, unter Linux und macOS also
  auch FIFOs und Sockets.
- Der **PKG Merger** meldete „beginnt nicht mit dem FIH-Header", wenn die
  Datei in Wahrheit gar nicht lesbar war. Dabei fielen drei fest deutsche
  Texte im Modul auf, die an der Übersetzung vorbeiliefen.
- Der **SELF-Inspektor** meldete beim Kopieren „Diagnosebericht wurde kopiert".
- Die **FileZilla-Suche** durchsuchte fest `C:\` und `D:\`.
- In den **Credits** ging das Mausrad unter Linux nicht, und das Autorenbild
  zeigte eine Hand, ohne klickbar zu sein.
- Das **Handbuch** hat 38 Seiten, nicht 30.

---

### Zum Umfang

Der Durchgang hat 41 Punkte behoben und **51 neue Prüfungen** hinterlassen,
darunter mehrere Anker: Prüfungen, die anschlagen, wenn die Voraussetzung
einer Behebung wegfällt und der Schutz damit ins Leere liefe.

Gesamtlauf: **2596 bestanden, 0 Fehlschläge.**

### Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.11.exe` | Windows 64-bit |
| `PS5_Dump_Image_Converter_v1.9.11_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.9.11.sha256` | Prüfsummen der Quelldateien |

Beide Programmdateien laufen eigenständig; es muss nichts nachinstalliert
werden.
