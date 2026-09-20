# PS5 Dump & Image Converter v1.9.34

Ein vorhandenes `.exFAT`-Backup lässt sich jetzt in **einem** Lauf mit
einem AMPR-EMU-Asset-Pack nachrüsten.

## Was fehlte

`.exFAT` als Quelle **und** als Ziel lief in „Quelle und Zielformat sind
identisch“, und eine Wegfunktion gab es im Programm gar nicht. Wer ein
Asset-Pack in sein Backup wollte, musste zweimal starten – erst nach
Dump-Ordner, dann zurück – oder das Format wechseln.

Bei `.ffpfsc` gibt es den Weg seit v1.9.20 (Aufgabe 2), bei `.ffpkg` baut
Aufgabe 4 sie ohnehin neu auf. Nur exFAT fehlte.

## Was jetzt geht

In **Aufgabe 6**: `.exFAT` als Quelle, `.exFAT` als Ziel, AMPR EMU angehakt,
Methode *Neue Methode (Asset-Pack)*. Das Abbild wird in einen
vorübergehenden Ordner entpackt, dort eingebaut, und daraus entsteht das
neue Abbild; der Ordner wird danach entfernt.

Das Selbst-Ziel ist weiterhin **nur** mit Asset-Pack wählbar – ohne ihn
entstünde eine Kopie derselben Datei. Eine Ja/Nein-Rückfrage gibt es
nicht: Ein Abbild in ein Abbild desselben Formats zu hüllen wäre Unsinn,
also ist der Neubau der einzig sinnvolle Weg.

An einem echten Spiel nachgemessen (Crazy Chicken Shooter, 253 MB):

| | Dateien im Abbild | Bänder | Größe |
| --- | --- | --- | --- |
| Backup ohne Pack | 72 | 0 | 253,8 MB |
| danach, mit Pack | 79 | 4 | 264,6 MB |

Dauer des zweiten Laufs: 12 Sekunden. Der Quell-Dump blieb unverändert.

## Aufgabe 6 kann jetzt alle drei Formate neu bauen

Beim Durchzählen der Selbst-Ziele fiel eine zweite Lücke auf: Die Wege für
`ffpfsc -> ffpfsc` und `ffpkg -> ffpkg` liegen längst in
`_execute_conversion_by_type` – nur die Sperre stand davor. Dieselbe
`.ffpkg`-Umwandlung ging in Aufgabe 4 anstandslos, in Aufgabe 6 nicht.

Gemessen, vorher und nachher (Sperre je Aufgabe und Format):

| Aufgabe | `.ffpfsc` | `.exFAT` | `.ffpkg` |
| --- | --- | --- | --- |
| 2 | mit Pack | – | – |
| 4 | – | – | immer |
| 6 **vorher** | gesperrt | gesperrt | gesperrt |
| 6 **jetzt** | mit Pack | mit Pack | immer |

„–“ heißt: Diese Quelle lässt die Aufgabe gar nicht zu.

## Warum nicht direkt in das Abbild schreiben

Der mitgelieferte exFAT-Schreiber ist ein *forward-only serializer*: Er
rechnet das Layout vorab aus und legt alles zusammenhängend ab
(`cluster_count = bitmap_clusters + content_clusters`). Eine Probe an einem
gebauten Abbild ergab **95 Zuordnungseinheiten, 95 belegt, 0 frei**. Eine
Datei nachträglich hineinzulegen hieße, das Abbild zu vergrößern und dabei
Bootbereich, FAT und Belegungskarte neu zu schreiben.

Hinzu kommt: Das Packwerkzeug des AMPR-Entwicklers arbeitet auf einem
echten Ordnerbaum (`--root <app0>`), nicht auf einem Abbild. Der
Zwischenordner ist also ohnehin nötig – du brauchst einmal die
Spielgröße an freiem Platz im Arbeitsordner.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.34.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.34_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.34_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.34.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
