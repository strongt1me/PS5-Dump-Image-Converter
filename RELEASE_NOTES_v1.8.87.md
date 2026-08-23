# PS5 Dump & Image Converter v1.8.87

**23.08.2026**

**PS4 PKG → ffpfsc** wurde einmal von Anfang bis Ende durchgemessen und gegen
die Beschreibung des Originalwerkzeugs gehalten. Diese Ausgabe hält fest, was
dabei herauskam — und behebt, was dabei auffiel.

## Die Funktion arbeitet korrekt

Ein vollständiger Durchlauf an einem echten Spiel, in **beiden**
Ausgabeformaten:

| Format | Größe | Prüfung |
| --- | --- | --- |
| `.ffpfsc` | 80,8 MB | 0 Warnungen, 0 Fehler |
| `.exfat` | 437,4 MB | gültige exFAT-Kennung und Bootsignatur |

Das **exFAT-Format war bislang nie erprobt** — es geht.

Die Bauform trifft die Vorgabe genau: ein äußeres komprimiertes Dateisystem
mit genau einer eingebetteten Datei, 64-KiB-Blöcke, Groß- und Kleinschreibung
egal. Auch die Begleitdatei `param.json`, an der ShadowMount+ das Spiel
erkennt, erfüllt alle sechs geforderten Punkte — kein BOM, Title-ID genau neun
Zeichen, Titel oben und unter `en-US`, `param.sfo` und `npbind.dat` daneben.

Ebenso geprüft: `verify` bestätigt das fertige Abbild, ein zweiter Bau ohne
`--force` nennt Datei und Abhilfe, nach einem Fehlschlag bleiben keine halben
Dateien liegen, und der Arbeitsordner schrumpft nach dem Lauf von 400 auf
6 MB.

## Wenn der Entpacker abstürzt, steht das jetzt da

An einem bestimmten Update-Paket stürzt der mitgelieferte Entpacker
reproduzierbar ab. Bisher lasen Sie:

```
extractor failed (3221225477) for ...pkg:
```

Eine nackte Dezimalzahl — und hinter dem Doppelpunkt nichts, denn ein
abgestürztes Programm hinterlässt keine Meldung. Wer das liest, sucht den
Fehler bei sich oder im Paket. Jetzt:

```
the extractor crashed (0xC0000005, memory access violation) while
extracting ...pkg. This is a fault in the bundled extractor, not in the
package or your setup; the same package may work in another version.
```

Dieselbe Übersetzung greift beim Einlesen, wo sonst nur
„extractor returned no JSON (exit 3221225477)" stand.

## Intel-Macs bekommen keinen unbrauchbaren Helfer mehr

In v1.8.86 war behoben worden, dass auf dem Mac die **Windows**-Datei gewählt
wurde. Dabei blieb eine Lücke: Die Mac-Fassung gibt es nur für **Apple
Silicon**, wurde auf einem Intel-Mac aber trotzdem angeboten — und scheiterte
beim Start mit „Bad CPU type in executable". Derselbe Fehler wie zuvor, nur
eine Stufe später.

Das Programm liest jetzt nach, für welchen Prozessor eine Datei gebaut ist:

| Rechner | Entpacker |
| --- | --- |
| Windows | die Windows-Fassung |
| Mac mit Apple Silicon | die Mac-Fassung |
| Mac mit Intel | keiner — das Fenster sagt es offen |
| Linux | keiner — dasselbe |

## Jetzt auf echter Apple-Hardware belegt

Für die macOS-Korrektur aus v1.8.86 stand hier: *„Nicht an echter Hardware
bestätigt."* Das ist erledigt. Der Bau-Lauf, der auf echten Macs läuft, sieht
seither im fertigen Programm nach, welche Datei gewählt wird und ob sie
anläuft:

| Rechner | Ergebnis |
| --- | --- |
| Apple Silicon | wählt die Mac-Fassung, der Entpacker startet |
| Intel | bietet richtigerweise gar nichts an |

**Diese Prüfung hat die Intel-Lücke selbst gefunden**, im allerersten Lauf.

## Für Entwickler

`UPSTREAM.md` — das Dokument, das festhält, was am eingebetteten Werkzeug
geändert wurde — behauptete „unverändert übernommen, mit einer Ausnahme". In
Wahrheit sind fünf Dateien geändert, und der Abschnitt zu den Plattformen
beschrieb sogar eine Absicht, die der Code nicht erfüllte: genau den
macOS-Fehler. Jetzt sind alle sieben Änderungen einzeln dokumentiert.

Ein Vergleich gegen den beiliegenden Quellauszug zeigt: Es wurde **kein
Fix des Originalprojekts verpasst**.

## Geprüft

**1297 Tests** laufen durch — neun mehr als in v1.8.86. Für jede Korrektur
wurde gegengeprüft, dass die Prüfungen ohne sie fehlschlagen.

Ein Hinweis in eigener Sache: Ein fehlender Import blieb von 1296 Tests
unbemerkt und fiel erst einer Quelltextprüfung auf. Die betroffene Stelle läuft
nur, wenn der Entpacker abstürzt — dafür gibt es jetzt einen echten Lauftest
statt einer reinen Textprüfung.

Das Benutzerhandbuch als PDF trägt weiterhin den Stand von v1.8.85; es wird
außerhalb der Bauumgebung erzeugt.
