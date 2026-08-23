# PS5 Dump & Image Converter v1.8.86

**23.08.2026**

Diese Ausgabe räumt mit Fehlermeldungen auf, die auf die falsche Fährte
führten — und behebt, dass **PS4 PKG → ffpfsc** auf dem Mac gar nicht lief.

## Werkzeugfenster: derselbe Knopf schließt wieder

Der zweite Druck auf denselben Knopf schließt das Fenster, das der erste
geöffnet hat. Das gilt für die Knöpfe der oberen Leiste, die Einträge unter
**WEITERE TOOLS**, das Rechtsklick-Menü und die eingefaltete Liste bei
schmalem Fenster.

Zwei Feinheiten:

* Läuft in einem Fenster gerade etwas, **bleibt es stehen** und kommt nach
  vorn. Das Schließen geht über den eigenen Weg des Fensters, damit seine
  Rückfragen und Abbruchwächter greifen — ein hartes Zumachen hätte einen
  Lauf mitten im Schreiben abschneiden können.
* Schließen Sie von Hand über das **X**, öffnet der nächste Druck wieder
  eines, statt ins Leere zu greifen.

**FileZilla** und das **Benutzerhandbuch** bleiben ausgenommen: Sie starten
ein fremdes Programm, da gibt es nichts umzuschalten.

## PS4 PKG → ffpfsc: die Meldungen sagen die Wahrheit

Drei Fehler führten in dieselbe Falle — die Ursache stand woanders, als die
Meldung behauptete.

| Was Sie lasen | Was wirklich los war |
| --- | --- |
| „Paket nicht unterstützt oder verschlüsselt" | Der **Zielpfad war zu lang**. Das Paket war einwandfrei. |
| „provide TITLE_ID or --all" — obwohl `--all` angegeben war | Es gab **kein brauchbares Spiel**. |
| gar nichts, der Fehlertext fehlte | Der Text enthielt ein Zeichen wie **®**, und daran ging die ganze Ausgabe verloren. |

Der dritte war der Schlüssel: Er verschluckte genau die Meldung, an der man
die beiden anderen hätte erkennen können.

### Die Pfadgrenze in Zahlen

Der mitgelieferte Entpacker endet bei **259 Zeichen**. Nachgemessen an
Tetris Ultimate:

| Zielpfad | Ergebnis |
| --- | --- |
| 175 Zeichen | vollständig, 113 Dateien |
| 183 Zeichen | vollständig, 113 Dateien |
| 186 Zeichen | Abbruch |

Das Programm **warnt jetzt vorher**, wenn es eng wird, und benennt hinterher
die tatsächliche Ursache samt Abhilfe: einen kürzeren Zielordner wählen.

## Der Arbeitsordner weicht aufs richtige Laufwerk aus

Wird der Pfad zu lang, legt das Programm seinen Arbeitsordner woanders an.
Das ging bisher **immer auf das Systemlaufwerk** — dorthin, wo Windows liegt
und der Platz meist am knappsten ist. Bei einem großen Spiel kann das die
Platte füllen.

Jetzt bleibt der Ausweichordner auf dem **Laufwerk Ihres Zielordners**:

| Zielordner | Arbeitsordner |
| --- | --- |
| `E:\Test` | bleibt: `E:\Test\ps4ffpsc_arbeit` |
| `E:\Spiele\PlayStation 4\Sicherungen\Fertig` | `E:\ps4ffpsc_arbeit` |
| `C:\Users\...\PS4 Konvertierung` | `C:\ps4ffpsc_arbeit` |

Die Schranke greift außerdem früher. Der alte Wert rechnete den **Spieltitel
im Ordnernamen** nicht mit und ließ nur zehn Zeichen Luft — ein Spiel mit
längerem Namen wäre gescheitert, und zwar mit der irreführenden Meldung von
oben.

## macOS: die Funktion lief gar nicht

Gemeldet von einem Nutzer mit Apple Silicon:

```
ps4ffpsc: [Errno 13] Permission denied: '.../bin/ps4_pkg_extract.exe'
```

Zwei Ursachen:

1. Im Programm liegen beide Fassungen des Entpackers nebeneinander — die für
   Windows und die für den Mac. Gewählt wurde **immer die für Windows**.
2. Beim Verpacken in das `.app` verlieren die Hilfsprogramme ihr
   Ausführungsrecht. Es wird jetzt nachgezogen.

Dasselbe betraf das **Einbetten von DLC**: Dort fiel der Helfer bisher
kommentarlos aus, ohne jede Meldung — man hätte es nur am ausbleibenden
Ergebnis gemerkt.

Für **Linux** gibt es weiterhin keinen Entpacker; das Programm sagt das beim
Öffnen des Fensters.

## Geprüft

**1288 Tests** laufen durch — 22 mehr als in v1.8.85. Die neuen decken die
Pfadgrenze, die Plattformauswahl, das Ausführungsrecht und den
Fenster-Umschalter ab; letzteren an echten Fenstern, nicht am Quelltext.

Für jede Korrektur wurde gegengeprüft, dass die Prüfungen ohne sie
**fehlschlagen** — sonst hätten sie nichts belegt.

Was **nicht** an echter Hardware bestätigt ist: die macOS-Korrektur. Hier
stand kein Mac zur Verfügung.
