# PS5 Dump & Image Converter v1.8.42 – Release Notes

## Zweck dieses Releases

Ein neuer Knopf für das Handbuch, eine abgeschnittene Zeile im Einstellungen-Fenster – und vier Fehlermeldungen, die es nie auf den Bildschirm geschafft haben. Dazu ist der Quelltext um 729 Zeilen unerreichbaren Code leichter geworden.

---

## Knopf BENUTZERHANDBUCH

In der Titelleiste, links neben **EN**. Ein Druck öffnet `BENUTZERHANDBUCH.html` im Standardprogramm; der Sprachumschalter beschriftet ihn auf Englisch mit **USER MANUAL**.

Die Datei wird über denselben Auflöser gesucht, den auch das Fenster CREDITS für die Lizenzdatei nutzt – im Skriptbetrieb neben der Quelldatei, in der EXE unter `sys._MEIPASS`. Fehlt sie, sagt das eine Meldung, statt still nichts zu tun.

Dabei kam heraus, dass das Handbuch bisher **gar nicht eingebettet** war. Es ist jetzt Teil der EXE, zusammen mit `README.md` und `CHANGELOG.md`, auf die es verlinkt – ohne die beiden wären das im entpackten Zustand tote Verweise.

---

## Vier Fehlermeldungen, die nie erschienen

Alle vier hingen an derselben Ursache. Python löscht den Namen aus `except ... as exc` beim Verlassen des Blocks. Ein Lambda, das ihn liest, wird hier aber über `after(0, ...)` erst später in der Tk-Schleife ausgeführt – dann ist der Name weg und der Rückruf stirbt an einem `NameError`:

```python
except Exception as exc:
    win.after(0, lambda: status_var.set(self._t("…", error=exc)))   # so nicht
```

Sichtbar war davon nichts, denn getroffen war genau der Weg, der den Fehler hätte melden sollen. Die Statuszeile blieb einfach stehen. Das umgebende `try/except` half nicht: Es schützt das Einplanen, nicht die spätere Ausführung.

| Betroffen | Wirkung |
| --- | --- |
| BACKPORT fehlgeschlagen | Grund wurde nie angezeigt |
| Remote-INI laden | Fehlschlag blieb unsichtbar |
| Remote-INI schreiben | Fehlschlag blieb unsichtbar |
| Debug-Log holen | Fehlschlag blieb unsichtbar |

Die Meldung wird jetzt noch im `except`-Block gebildet; eingefangen wird nur der fertige Text.

Abgesichert über den Syntaxbaum statt über die vier bekannten Zeilen: Kein Lambda und keine verschachtelte Funktion in einem `except`-Block darf die Ausnahmevariable lesen, sofern sie sie nicht selbst bindet. Dazu zwei Gegenproben – dass die Regel den Fehler überhaupt erkennt, und dass sie die sichere Form `lambda e=str(exc):` nicht fälschlich meldet.

---

## Einstellungen: Hinweiszeile war abgeschnitten

Der Hinweis „Änderungen wirken sofort; Speichern sichert sie und schließt." stand mit den beiden Knöpfen in **einer** Zeile und hatte eine feste Umbruchbreite von 300 Pixeln. Der Dialog ist 520 breit, die Knöpfe nehmen gut 200 – der Text lief unter sie und wurde abgeschnitten. Auf Englisch ist er noch länger.

Hinweis und Knöpfe haben jetzt getrennte Zeilen, der Hinweis steht darüber und bricht auf die tatsächliche Breite um, also auch nach Vergrößern des Fensters richtig.

---

## 729 Zeilen unerreichbarer Code entfernt

Eine Durchsicht mit pyflakes und vulture, jeder Treffer einzeln nachgeprüft – von 30 Kandidaten waren 16 falsch (Framework-Rückrufe und Methoden, die über Namensstrings aufgerufen werden).

| Entfernt | Zeilen |
| --- | --- |
| `_ensure_dokan` – zweite, unerreichbare Dokan-Installation | 186 |
| `_compress_pfs_zstd` | 145 |
| FileZilla-Quick-Connect, vier Methoden | 175 |
| `_parallel_copy_files` | 53 |
| `_estimate_step_eta_seconds` | 35 |
| Release-Test-Gate, drei Methoden | 46 |
| `_compute_exfat_image_size`, `_toggle_fullscreen`, Copy-Metriken | 65 |
| tote Importe und ungenutzte lokale Variablen | 24 |

Das lief in zwei Wellen: Nach der ersten Löschung verwaisten drei weitere Funktionen, die vorher noch Aufrufer hatten.

Der eingebaute FTP-Client entfiel mit v1.8.40 – die Quick-Connect-Kette hat dabei ihren Einstieg verloren und stand seither ohne Aufrufer da. In ihr steckte auch ein alter Bekannter: Lesezugriffe auf `self._settings`, ein Attribut, das im ganzen Programm nirgends gesetzt wird. Ein Fehler ohne Wirkung, weil ihn niemand erreichen konnte.

Dazu entfielen 38 Übersetzungsschlüssel, die erst durch diese Löschung verwaist sind. Der Bestand ist gegen den Stand davor gemessen, damit nur zugeordnete Einträge fallen. Unberührt bleiben Importe mit `# noqa: F401` – das sind absichtliche Verfügbarkeitsprüfungen, keine Reste.

Die Dokan-Installation, die beim Einhängen tatsächlich erscheint, ist davon nicht betroffen: Sie läuft über `_run_background_installer`, nicht über das entfernte `_ensure_dokan`.

---

## Tests

Neu sind `test_handbuch_knopf.py` (17 Fälle) und `test_ausnahme_lambda.py` (5 Fälle). Zusammen **498 unittest-Fälle grün**, dazu 14/14 und 8/8 aus den eigenen Sammlungen; 43 Testdateien ohne Fehlschlag.

Zusätzlich geprüft:

- pyflakes über die Hauptquelle: **0 undefinierte Namen** (vorher 4)
- Smoke-Test der vollen Oberfläche nach der Löschung: `GUI_SMOKE_OK; FFPKG_PROGRESS_GUI_SYNC_OK; BG_IMAGE_CONTENT_AREA_OK; BG_IMAGE_CARD_OK`
- Kaskadenprüfung bis zur Stabilität – nach der zweiten Welle blieben nur die drei HTTP-Rückrufe übrig, die das Framework aufruft

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.42.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.42.sha256` | Prüfsummen aller Quelldateien |
| `BENUTZERHANDBUCH.html` / `.pdf` | Handbuch, Werkzeugleisten-Tabelle um den neuen Knopf ergänzt |
| `test_handbuch_knopf.py`, `test_ausnahme_lambda.py` | neue Tests |
