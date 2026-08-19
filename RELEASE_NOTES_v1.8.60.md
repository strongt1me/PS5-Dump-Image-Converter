# PS5 Dump & Image Converter v1.8.60 – Release Notes

## Zweck dieses Releases

In **elf von vierzehn** Werkzeugfenstern lag die unterste Knopfreihe außerhalb des Fensters. Man musste jedes Mal erst am Rand ziehen, um an „Schließen" zu kommen.

Gemeldet als „einige Fenster, bei denen man nicht an die Knöpfe gelangt". Es waren fast alle.

---

## Wie der Umfang festgestellt wurde

Grundlage war eine Bildschirmaufnahme von 12:12 Minuten. Daraus alle 6 Sekunden ein Einzelbild (122 Stück), zu acht Kontaktbögen zusammengefasst, Verdächtiges im Vollbild nachgesehen.

**Die Bögen lieferten den Verdacht, nicht den Beweis.** Ein Einzelbild zeigt, dass ein Fenster keine Knöpfe hat — nicht, ob es zu klein ist oder ob es dort schlicht keine gibt. Deshalb der zweite Schritt: **jedes Werkzeugfenster geöffnet und ausgemessen**, eingestellte Größe gegen die Größe, die der Inhalt braucht.

| Fenster | fehlte | im Video |
| --- | --- | --- |
| AMPR-Index-Builder | **265 px hoch** | 8:24–9:06 |
| PKG-Merger | 257 breit, 120 hoch | – |
| Backport | 244 px breit | – |
| Bibliothek | 237 breit, 125 hoch | 2:36–3:06 |
| Diagnosebericht | 137 hoch, 14 breit | 1:12–1:18 |
| JS Loader | 101 px hoch | 4:48–4:54 |
| KLOG | 90 px hoch | 2:00, 2:24 |
| Debug-.pkg bauen | 76 px hoch | 11:30, 11:54 |
| Dump umbenennen | 57 px hoch | **10:06–10:42** |
| Design | 48 px breit | – |
| Downloads | 27 px hoch | 6:48 |

Am deutlichsten bei **Dump umbenennen**: Von 10:06 bis 10:42 endet das Fenster nach dem Eingabefeld; „Umbenennen" und „Schließen" erscheinen erst ab 10:54, nachdem der Nutzer es größer gezogen hat.

---

## Die Ursache, und warum es ein Fix statt elf ist

Alle diese Fenster entstehen über `_build_modern_toplevel`, und ihre Maße stehen als feste Zahlen im Aufruf. Wächst der Inhalt — eine Zeile mehr, ein längerer Text, eine zusätzliche Schaltfläche —, bleibt die Zahl stehen und die unterste Reihe rutscht hinaus.

Jedes Fenster fragt jetzt **seinen eigenen Inhalt**, was er braucht, und wächst darauf. Der Bildschirm ist die Obergrenze: Ein Fenster, das nicht hineinpasst, wird so groß wie möglich — unerreichbare Knöpfe wären schlimmer als ein randvolles Fenster. Die Mindestgröße zieht mit, sonst ließe es sich sofort wieder zu klein schrumpfen.

### Die Falle dabei

Der erste Versuch hängte die Anpassung an `after_idle`. Sie lief — und änderte nichts.

**Mehrere Erbauer rufen selbst `update_idletasks()`**, und das führt die Rückmeldung aus, bevor ein einziges Bedienelement drinsteht. Gemessen am AMPR-Fenster: blieb bei 700×460, obwohl es 725 braucht. Jetzt zwei verzögerte Anläufe (80 und 400 ms); der zweite fängt Inhalte ab, die erst nachträglich eintreffen. Die Prüfung vergrößert nur und ist damit gefahrlos wiederholbar.

Ein Test verbietet die Rückkehr zu `after_idle` ausdrücklich.

---

## Anzeige

- **Die Protokollfläche lässt jetzt 30 % des Hintergrundbildes durchscheinen** (Deckkraft 0,70), als eigene Konstante getrennt von der Kartentönung (0,18). Die Fläche ist groß und dauerhaft sichtbar; was bei einer Karte dezent wirkt, ist dort etwas anderes.
  **Einschränkung:** Tk kann ein Textfeld nicht wirklich durchsichtig machen. Der Eindruck entsteht durch Mischen der Flächenfarbe mit dem Bild — dieselbe Technik wie bei den Karten.
- **Ein falsches Anführungszeichen** in der Meldung beim Umbenennen: `„{name}"` — typografisch geöffnet, gerade geschlossen. Alle 2600 sichtbaren Texte nachgezählt, das war die einzige Fundstelle.

---

## Nachgereicht in derselben Version

### Das Hintergrundbild sprang an der Kartenkante

Gemeldet mit einem Bildausschnitt, in dem dasselbe Motiv versetzt zweimal erscheint. Ursache war ein Fehler aus **v1.8.55**: Damals wurde die Skalierung an acht Stellen von „strecken" auf „formatfüllend beschneiden" umgestellt. Die Karte zeichnet ihren Untergrund aber aus einer neunten Quelle, `_bg_image_raw`, und die blieb bei `resize()`.

Seither benutzten Karte und Umgebung zwei verschiedene Geometrien für dasselbe Bild — an der Kartenkante sprang das Motiv.

**Warum die Prüfung es nicht gefunden hat:** Der Test aus v1.8.55 verbietet den Rückfall auf `resize()`, sah aber nur nach `_bg_image_cache` und `_sidebar_bg_image_cache`. Die zwei betroffenen Zeilen lagen genau im blinden Fleck der Prüfung, die sie hätte fangen sollen. Sie deckt jetzt alle drei Bildquellen ab.

### Die Knopfleiste zeigte das Bild ein zweites Mal

Nach dem Fix an der Kartenkante blieb eine Fläche übrig: die Leiste mit „Starten", „Abbrechen" und der Größenanzeige („1.05 GB → ~336.6 MB"). Sie zeigte ihren Bildausschnitt unverändert, während Karte und Protokollfläche darüber und darunter gedämpft sind — das Motiv wirkte dadurch versetzt wiederholt.

Sie bekommt dieselbe Behandlung wie die Protokollfläche: **Deckkraft 0,70**, das Bild scheint noch zu 30 % durch.

**Zwei Zeichenstellen, nicht eine:** Die Leiste zeichnet ihr Bild einmal beim Aufbau und einmal beim Ändern der Fenstergröße. Ein Fix nur an der ersten hätte gehalten, bis jemand das Fenster zieht. Ein Test geht jetzt beide Stellen durch, statt sich auf die eine zu verlassen.

### Das dritte Feld hatte keinen Namen

In der Bedienzeile stehen Kompression, Worker-Threads und Prüfung nebeneinander. Die Zeilenüberschrift nannte nur die ersten beiden; beim dritten stand lediglich „Schnell", ohne dass erkennbar war, wozu.

Rechts daneben steht jetzt **„PRÜFUNG NACH DEM PACKEN"**, und die Überschrift nennt alle drei Felder.

### Das Zahlenfeld war zu niedrig

Gemessen 27 gegen 37 Pixel: ttk gibt einer Klappliste mehr Innenabstand als einem Zahlenfeld, dieselbe Schrift allein gleicht das nicht aus. Die Differenz wird jetzt **gemessen statt geraten** — Themes und Anzeigeskalierung ändern die Innenabstände, eine feste Zahl wäre auf dem nächsten System wieder falsch. Alle drei Felder sind 37 Pixel hoch.

### Drei neue AMPR-EMU-Fassungen

**0.3.1, 0.3.4 und 0.3.5** liegen bei und stehen im AMPR EMU Manager ganz oben. Am Programm war nichts zu ändern: Der Versionsspeicher wird eingelesen, und die Bau-Beschreibungen nehmen den ganzen Ordner mit.

**Knapp war es trotzdem:** Die Ordner entstanden in derselben Minute, in der die EXE gebaut wurde, und die Übertragung nach WSL war schon durch. Beide Fassungen hätten die neuen Dateien nicht enthalten — und einer EXE mit dreizehn statt sechzehn Einträgen sieht man das von außen nicht an. Deshalb wird jetzt im fertigen Programm nachgesehen, ob `0.3.5 no debug` darin vorkommt, statt es anzunehmen.

---

## Zwei Fehlalarme aus der Durchsicht

- Das Raster grauer Rechtecke bei 8:00 sind die **Snap-Layouts von Windows 11**, eingeblendet weil der Zeiger über dem Maximieren-Knopf stand.
- Die halb schwarzen Ordner-Auswahlfenster bei 5:24 und 5:30 sind **Windows' eigene Dialoge** während des Öffnens.

Beide wären aus dem Kontaktbogen heraus „behoben" worden — an Stellen, die nicht kaputt sind.

---

## Was die Durchsicht *nicht* ergeben hat

Keine abgeschnittenen Beschriftungen, keine falsch sitzenden Tabellenköpfe, keine Zeichenreste, kein Flackern beim Fensterwechsel.

**Eine Einschränkung:** Abgetastet wurde alle 6 Sekunden. Ein Fehler, der nur kurz aufblitzt, kann durch das Raster gefallen sein. Die Fortschrittsanzeige kam nicht vor — es wurde keine Umwandlung gestartet.

---

## Tests

**837 Prüfungen, 0 Fehlschläge.** Neun neue messen jedes Fenster gegen seinen Inhalt; die Prüfung gegen zurückfallende Skalierung deckt jetzt alle drei Bildquellen ab statt zwei.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.60.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.60_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.60_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.60_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.60.sha256` | Prüfsummen aller Quelldateien |
