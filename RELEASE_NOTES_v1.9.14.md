Die Bibliothek zeigt deine Spiele jetzt als Titelbilder statt als
Dateinamen – wahlweise die auf dem Rechner oder die auf der PS5 – und kann
Abbilder in beide Richtungen übertragen. Dazu hat das Werkzeug „App direkt
installieren" eine Anleitung bekommen, die erklärt, wofür es gut ist.

## Die Bibliothek: Cover statt Text

Die alte Bibliothek war eine Liste mit Dateinamen. Jetzt gibt es eine
Kachelansicht mit dem Titelbild jedes Spiels; ein Knopf schaltet auf die
gewohnte Liste zurück, und die Wahl wird gemerkt.

Namen und Titelbilder kommen aus derselben Quelle wie bei den Aufgaben 1–8:
aus der `param.json` und dem `icon0.png` im Abbild selbst. Ein einmal
geöffnetes Titelbild bleibt auf der Platte liegen – beim nächsten Öffnen ist
es sofort da, statt dass jeder Container noch einmal aufgemacht wird.

### Zwei Quellen

**Rechner.** Deine Ordner, jetzt rekursiv durchsucht. Bisher ging der
Suchlauf nur eine Ebene tief: Wer seine Sicherungen in
`Downloads/PS5/Spiele/…` abgelegt hatte, sah eine leere Liste. Gefunden
werden alle fünf Bauformen – `.ffpfsc`, `.ffpfs`, `.exfat`, `.ffpkg` und
Dump-Ordner.

**PS5.** Was auf der Konsole liegt. Gesucht wird an allen gängigen
Ablageorten, auch an denen anderer Verwalter:

| Ort | Wer legt dort ab |
| --- | --- |
| `/data/games` | Itemzflow |
| `/data/homebrew` | ShadowMount+, Dump Runner |
| `/data/etaHEN/games`, `/data/etaHEN/PS5` | etaHEN |
| `/mnt/usb0…7/{games,homebrew,etaHEN/games}` | USB-Datenträger |
| `/mnt/ext0…1/{games,homebrew,data/games}` | M.2-Erweiterung |

An der Konsole gemessen (12.09.2026): **16 Titel in 1,6 Sekunden, 15 davon
mit Titelbild.** Ein Dump-Ordner bringt seine Angaben selbst mit; für
Abbilder, deren Dateiname keine Title-ID trägt, gleicht das Programm den
Namen gegen das ab, was die Konsole über jedes je gesehene Spiel führt.
Passen zwei Titel, wird keiner genommen – ein falsches Titelbild wäre
schlimmer als gar keines, weil es richtig aussieht.

Was **nicht** mehr in der Liste steht: `GAMES`, `GAMEI`, der Papierkorb und
die Ablageorte selbst. Ein Ordner gilt nur als Spiel, wenn `sce_sys` oder
`eboot.bin` darin liegt.

### Hoch- und herunterladen

Ein Abbild vom Rechner auf die PS5 schicken oder von dort holen, mit
Fortschrittsanzeige. Ordner sind bewusst ausgenommen: Ein Dump besteht aus
zehntausenden Dateien, das dauert über FTP Stunden – und die Konsole startet
ihn von dort ohnehin nicht.

> **Zum Abbrechen eines Downloads:** Das legt den FTP-Dienst der PS5 lahm.
> Sie nimmt danach keine Verbindung mehr an und muss neu gestartet werden.
> Das ist an der Konsole gemessen, nicht vermutet. Der Abbrechen-Knopf fragt
> deshalb vorher nach. Beim Hochladen ist ein Abbruch harmlos, dort entfällt
> die Frage.

## „App direkt installieren" erklärt sich jetzt

Über den Feldern standen drei Absätze – vollständig, mit allen gemessenen
Fehlercodes, und trotzdem unverständlich. Sie fingen damit an, was das
Werkzeug technisch tut (`sceAppInstUtilAppInstallAll`), und beantworteten
nie die Frage, die man zuerst hat: *Wofür brauche ich das, und was mache ich
jetzt?*

Im Fenster stehen jetzt zwei Sätze. Der Rest liegt hinter dem Knopf
**Anleitung**: eine Seite im Browser, im Stil des Benutzerhandbuchs, mit
sieben Abschnitten – was ist das, wofür, was brauche ich vorher, Schritt für
Schritt, was passiert dabei auf der Konsole, was die Fehlercodes bedeuten,
und woher das alles bekannt ist. Auf Deutsch und Englisch, passend zur
eingestellten Sprache.

## Kleineres

- Der Hinweis unter der Zielformat-Liste nahm bei `.ffpfsc` und `.ffpfs`
  vier Zeilen ein und drängte das Statusprotokoll nach unten. Es sind jetzt
  drei, mit derselben Aussage: Die beiden Texte waren länger als die
  Umbruchgrenze und brachen deshalb jeweils auf zwei Zeilen um. Derselbe
  Fall bei `.exFAT` war schon länger da und ist mit behoben.
- Das Bibliotheksfenster ließ sich so klein ziehen, dass „Als Quelle
  übernehmen" auf gut die Hälfte zusammengedrückt wurde und die Beschriftung
  abgeschnitten war. Die Mindestbreite entspricht jetzt dem, was die
  Knopfreihe wirklich braucht.

## Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.14.exe` | Windows 64-bit |
| `SOURCE_FILE_MANIFEST_v1.9.14.sha256` | Prüfsummen der Quelldateien |

Die Programmdatei läuft eigenständig; es muss nichts nachinstalliert werden.
