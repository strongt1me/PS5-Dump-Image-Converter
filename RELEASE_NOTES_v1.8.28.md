# PS5 Dump & Image Converter v1.8.28 – Release Notes

## Zweck dieses Releases

Version **v1.8.28** beseitigt die farbigen Flächen hinter den Beschriftungen des Hauptfensters. Bei eingestelltem Hintergrundbild stand hinter QUELLE, ZIELFORMAT, KOMPRESSION, ZIELORDNER und TEMP-ORDNER ein heller Kasten; dasselbe galt in schwächerer Form für Überschrift, Untertitel, Statuszeile und die Sidebar-Beschriftungen. Der Formathinweis unter dem Zielformat zeigte sogar eine vollflächige Kartenfarbe. Alle diese Texte stehen jetzt ohne sichtbare Fläche auf dem Hintergrundbild.

## Änderungen im Einzelnen

### 1. Tatsächliche Ursache

Nicht der untergelegte Bildausschnitt war falsch. Eine Messung am laufenden Programm zeigt, dass er pixelgenau mit dem Kartenhintergrund an derselben Stelle übereinstimmt – Stichproben über `photo get x y` gegen den erwarteten Ausschnitt ergaben identische RGB-Werte.

Der Kasten war die Polsterung, die ein Label ringsum um seinen Inhalt legt: `ttk.Label` legt über die Elementhierarchie `Label.border` → `Label.padding` je 2 px an, `tk.Label` zusätzlich `padx`/`pady` und einen Rahmen. Diese Streifen werden in der Hintergrundfarbe des Widgets gezeichnet (`bg_card` bzw. `bg_main`), während das Bild mit `compound="center"` nur innerhalb davon zentriert wird. Gemessen: Label 62 × 28 Pixel bei einem Bild von 58 × 24 Pixeln. Nebenwirkung war ein zusätzlicher Versatz – der Ausschnitt wurde für die Label-Position berechnet, aber 2 px weiter innen gezeichnet.

### 2. `_make_caption_borderless()`

Neue Methode, die einer Beschriftung die Polsterung nimmt: bei `ttk.Label` über `padding=0, borderwidth=0`, bei `tk.Label` über `padx=0, pady=0, borderwidth=0, highlightthickness=0`. Danach deckt das Bild das Label vollständig ab (Label-Größe = Bildgröße), sichtbar bleibt nur die Schrift.

Sie wird pro Beschriftung genau einmal ausgeführt (Merker `_caption_borderless`) und verwirft dabei die zwischengespeicherte Textgröße, die noch die Polsterung enthielt. Der Merker ist notwendig: Die Größenänderung löst ein `<Configure>` aus, das über die `_on_*_configure`-Handler wieder in dieselbe Zeichenfunktion führen kann – genau die Endlosschleife, vor der der Kommentar in `_redraw_card_captions` warnt.

Aufgerufen wird sie in allen drei Zeichenschleifen: `_redraw_card_captions`, `_redraw_content_captions` und `_redraw_sidebar_captions`. Damit gilt die Änderung für die Karten-Beschriftungen, für Überschrift, Untertitel, Größenangabe und Statuszeile sowie für die Sidebar.

### 3. Formathinweis mit Bildausschnitt

`format_info_label` („Quelle: Dump-Ordner") hatte bisher gar keinen untergelegten Ausschnitt und stand deshalb als deckende `bg_card`-Fläche mitten zwischen den übrigen Beschriftungen. Es gehört jetzt zu `_card_caption_labels` und wird wie diese behandelt.

### 4. Neuzeichnen bei Wechseln

Die Zeichenschleife der Karte überspringt jetzt ausgeblendete Beschriftungen (`winfo_ismapped`), weil `ZIELFORMAT` und der Formathinweis je nach Aufgabe aus dem Raster genommen werden und dann veraltete Koordinaten liefern.

Damit sie beim Wiedereinblenden ihren Ausschnitt bekommen, stößt die neue Methode `_schedule_caption_redraw()` das Zuschneiden über `after_idle` an – aufgerufen aus `_refresh_target_format_options` (Aufgaben- und Sprachwechsel ändern Sichtbarkeit, Text und damit Größe und Position) sowie aus `_update_sidebar_preview` (der Spielname unter dem Cover erscheint erst, wenn die Quelle eingelesen ist).

### 5. Unverändert

Die halbdeckende Fläche hinter der Größenangabe der Aktionsleiste bleibt bestehen (`_caption_backdrop_opacity = 0.80`). Sie ist keine Panne, sondern hält die Angabe über unruhigen Bildbereichen lesbar.

## Bedeutung für Nutzer

- Das Hintergrundbild läuft ohne unterbrechende Kästen durch das Fenster.
- Der Effekt gilt in allen drei Farbschemata und in beiden Sprachen.
- Ohne eingestelltes Hintergrundbild ändert sich das Erscheinungsbild nicht.

## Verifikation

Gemessen am laufenden Programm, nicht nur am Quelltext. Für jede Beschriftung wurde geprüft, ob das Bild das Label vollständig abdeckt (Label-Größe = Bildgröße) und ob seine Pixel mit dem Untergrund an derselben Stelle übereinstimmen:

- Startzustand: alle sechs Karten-Beschriftungen randlos und deckungsgleich.
- Nach Wechsel auf Aufgabe 7 und zurück auf Aufgabe 1: unverändert deckungsgleich; ausgeblendete Beschriftungen werden übersprungen und beim Wiedereinblenden neu zugeschnitten.
- Nach Sprachwechsel (abweichende Textbreiten): weiterhin deckungsgleich.
- Content-Bereich: Überschrift, Untertitel, Größenangabe und Statuszeile randlos.
- Sidebar: Symbolzeile, Titel, Untertitel randlos; der Spielname unter dem Cover erhält seinen Ausschnitt, sobald er eingeblendet wird (beide Zweige von `_update_sidebar_preview` geprüft).
- `test_background_image.py`, `test_i18n.py`, `test_ini_config.py`, `test_build_ready.py`, `test_all_quality.py`, `test_all_quality_new.py`: 26/26 bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.28** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.28.sha256`

Die Datumsangabe des v1.8.27-Eintrags im Changelog stand auf dem 16.08.2026 und wurde auf den tatsächlichen Tag (15.08.2026) berichtigt.

Das Manifest umfasst **215 Einträge** (v1.8.27: 203). Neu aufgenommen sind die zehn Sidebar-Hintergrundbilder `Hintergrundbilder/s01…s10`, die zwar in die EXE eingebettet werden, im vorherigen Manifest aber fehlten, sowie die Release Notes dieser Version und das Manifest der Vorversion. Unverändert außerhalb des Manifests bleiben `ARBEITSSTAND_2026-08-15.md`, `Benutzerhandbuch.pdf` und `Hintergrund Bild-Main.png`.

## Windows-EXE

`dist\PS5_Dump_Image_Converter_v1.8.28.exe`, 83,8 MB, mit `Build_EXE.ps1` in einer normalen Shell gebaut (Exit-Code 0, PyInstaller über `.venv`, Python 3.14.6).

Im Archiv der fertigen EXE nachgewiesen: 20 Hintergrundbilder, 24 Dateien aus `PlayGo & AMPR_EMU`, 24 Payloads aus `helloworld`. Die Versionsressource der Datei meldet `1.8.28.0` unter dem Namen `PS5_Dump_Image_Converter_v1.8.28.exe`.
