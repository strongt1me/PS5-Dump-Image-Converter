# PS5 Dump & Image Converter v1.8.29 – Release Notes

## Zweck dieses Releases

Version **v1.8.28** hatte die Beschriftungen randlos gemacht; eine Bildschirmaufzeichnung der laufenden EXE zeigte danach drei verbliebene Stellen, an denen weiterhin farbige Flächen auf dem Hintergrundbild standen. Diese Version beseitigt sie und ergänzt die Farbnachführung beim Design-Wechsel.

Zusätzlich wird der bereits mitgelieferte FTP-Payload **zftpd** endlich von der Automatik gefunden, und die Lizenzen der mitgelieferten Fremdkomponenten liegen dem Programm jetzt bei.

## Änderungen im Einzelnen

### 1. Telemetrie-Anzeige im Leerlauf

`telemetry_label` wurde außerhalb einer laufenden Aufgabe nur geleert, nicht ausgeblendet. Ein leeres `ttk.Label` ist trotzdem 4 × 21 Pixel groß (Polsterung plus Zeilenhöhe) und malt darin seine Widget-Farbe – im hellen Design also eine weiße Fläche in der unteren rechten Ecke, dauerhaft sichtbar.

Es wird jetzt per `grid_remove()` aus dem Raster genommen, wie das benachbarte `percent_label` es schon tat, und erst mit dem ersten Messwert wieder eingeblendet. Sichtbar gehört es zu `_content_caption_labels` und bekommt damit denselben Bildausschnitt wie alle übrigen Beschriftungen – sonst stünde während einer Aufgabe genau derselbe Kasten dort, nur mit Text darin. Da sich der Text sekündlich ändert und damit die Breite, stößt jede Textänderung ein Neuzuschneiden an.

### 2. Größenanzeige der Aktionsleiste

`size_label` hatte eine feste Breite von 64 Zeichen (~440 px). Seine bewusst halbdeckende Fläche (`_caption_backdrop_opacity = 0.80`, hält die Angabe über unruhigen Bildbereichen lesbar) wurde deshalb über die volle Labelbreite gezogen, auch wenn nur „618.4 MB" darin stand – auf dem Hintergrundbild wirkte das wie eine zweite, leere Fortschrittsleiste.

Die feste Breite entfällt. Der Platz wird ohnehin von der Spalte selbst reserviert (`grid_columnconfigure(4, weight=0, minsize=520)`), das Label darf also genau so breit sein wie sein Text. Nachgemessen an drei Textlängen:

| Text | Label | Fläche | Position der Spalte |
| --- | --- | --- | --- |
| „618.4 MB" | 68 × 20 | 68 × 20 | x = 842 |
| „618.4 MB → ~347.6 MB" | 168 × 20 | 168 × 20 | x = 842 |
| lang, mit ETA, Temp und Zielpfad | 489 × 40 (zwei Zeilen) | 489 × 40 | x = 842 |

Spalte und Knöpfe bleiben in allen Fällen an derselben Stelle. Nutzbar sind jetzt 520 px statt der bisherigen 440 px, `wraplength` bricht längere Angaben wie bisher innerhalb dieser Breite um – Platz geht keiner verloren.

### 3. Startphase und Größenänderung

Beide Fälle hatten keinen Nachzieher: `_on_root_configure` steigt während der Startphase per `_startup_complete` bewusst aus, und beim Ziehen am Fensterrand werden nur die Hintergrundflächen entprellt neu gerechnet, nicht die Ausschnitte darauf. Die Beschriftungen trugen dadurch den Ausschnitt der alten Geometrie, der an der neuen Stelle als Kasten sichtbar wird.

- `_redraw_all_captions()` fasst die drei Zeichenfunktionen zusammen.
- `_finish_startup_phase()` (700 ms nach dem Start) schneidet einmal alles nach.
- `_on_root_configure` plant 160 ms nach der letzten Größenänderung `_on_layout_settled()` ein – bewusst später als das Bild-Resize (80 ms), damit zuerst die Flächen und dann die Ausschnitte darauf entstehen.

Nicht geändert wurde die Entprellung selbst: Während des Ziehens hinken die Hintergrundbilder weiterhin rund 80 ms hinterher. Ohne sie würde bei jedem Pixel das gesamte Bild neu skaliert.

### 4. Schriftfarben beim Design-Wechsel

Ein Teil der Beschriftungen setzt seine Farbe direkt am Widget statt über den ttk-Style – die Karten- und Content-Beschriftungen, weil sie den Bildausschnitt als Kompound-Bild tragen, die Sidebar-Beschriftungen, weil sie gewöhnliche `tk.Label` sind. `_setup_styles()` erreicht sie deshalb nicht. In `_apply_theme` gab es dafür Einzelzeilen, die die Größenanzeige abweichend von ihrer Erstellungsfarbe auf `fg_secondary` setzten und Telemetrie sowie Sidebar gar nicht erfassten.

Jedes betroffene Label trägt jetzt seine Farbrolle als Eigenschaft (`_caption_fg_role`), und `_apply_caption_colors()` zieht daraus alle Farben nach. Labels ohne Rolle werden übersprungen – deren Farbe kommt aus dem Style und ist nach `_setup_styles()` bereits richtig.

### 5. zftpd: Port, Hinweis, Lizenz

**Port.** Neue Konstante `PS5_FTP_PORTS = (2121, 2120, 1337, 21)`, deren Reihenfolge zugleich die Suchreihenfolge ist: ftpsrv (2121) als verbreitetster Fall, dann zftpd (2120), etaHEN (1337), klassisch (21). Angebunden sind `_AMPR_FTP_PORTS`, beide Dialog-Vorgaben, die FTP/SFTP-Umschaltung und der CLI-Hilfetext – Letzterer liest die Ports aus der Konstante und kann daher nicht mehr veralten.

Bisher kannte die Automatik nur 2121, 1337 und 21. Die beiden mitgelieferten zftpd-Payloads (`helloworld/zftpd-ps5-v1.5.0.elf` und `-zhttp-`) lauschen auf Konsolen jedoch auf **2120**; 2121 ist deren POSIX-Vorgabe. Wer sie über den JS Loader startete, wurde nicht gefunden.

**Hinweis.** Scheitert die Verbindung im AMPR Picker, nennt das Protokoll jetzt die geprüften Ports und den Weg zur Lösung – zftpd (Port 2120, sättigt laut Projektangabe eine Gigabit-Leitung) oder ftpsrv-ps5 (2121). Neuer Übersetzungsschlüssel `ampr.picker_connect_hint` in beiden Sprachen.

**Lizenz.** zftpd steht unter MIT; die Lizenz verlangt, dass Copyright- und Lizenztext jeder Weitergabe beiliegen. Neue Datei `THIRD_PARTY_LICENSES.md` mit dem vollständigen Text, den betroffenen Binärdateien und einem Absatz zu den übrigen Payloads. Sie wird über die `.spec` in die EXE eingebettet und ist im Fenster CREDITS über einen eigenen Eintrag aufrufbar; dazu kommen Links auf seregonwar und das zftpd-Projekt.

## Bedeutung für Nutzer

- Auf dem Hintergrundbild steht keine farbige Restfläche mehr – weder im Leerlauf noch beim Start oder beim Verändern der Fenstergröße.
- Der schnellste mitgelieferte FTP-Payload lässt sich ohne manuelle Portangabe verwenden.
- Findet die Konsole sich nicht, sagt die Meldung, was zu tun ist.

## Verifikation

Gemessen am laufenden Programm:

- Telemetrie: im Leerlauf nicht im Raster (1 × 1, kein Bild), während einer Aufgabe 444 × 17 mit deckungsgleichem Bild, danach wieder ausgeblendet.
- Größenanzeige: drei Textlängen geprüft (siehe Tabelle), Label und Fläche stets deckungsgleich, Spaltenposition unverändert, kein Text abgeschnitten.
- Startphase: ab 600 ms sind alle sichtbaren Beschriftungen deckungsgleich.
- Größenänderung auf 1500 × 900: alle Beschriftungen aus allen drei Listen deckungsgleich.
- Design-Wechsel über hell, mittel und dunkel: acht stellvertretende Beschriftungen tragen in jedem Design die Farbe ihrer Rolle, keine Abweichung.
- Ports: `--ampr-port` meldet „automatisch 2121/2120/1337/21 probieren", `_AMPR_FTP_PORTS` enthält alle vier.
- Ressourcen-Fenster: die drei neuen Einträge (seregonwar, zftpd, Lizenzdatei) sind vorhanden; `_bundled_resource("THIRD_PARTY_LICENSES.md")` löst auf.
- `test_background_image.py`, `test_i18n.py`, `test_ini_config.py`, `test_build_ready.py`, `test_all_quality.py`, `test_all_quality_new.py`: 26/26 bestanden; `test_build_ready.py` zusätzlich 8/8 als Build-Freigabe.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.29** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.29.sha256`

Neu im Projekt: `THIRD_PARTY_LICENSES.md`.
