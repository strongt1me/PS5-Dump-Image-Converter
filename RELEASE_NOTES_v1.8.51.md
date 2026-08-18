# PS5 Dump & Image Converter v1.8.51 – Release Notes

## Zweck dieses Releases

Die `sce_sys/param.json` wurde bisher nur daraufhin geprüft, ob sie sich als JSON lesen lässt. Das ist zu wenig: Was diese Prüfung passiert, kann auf der Konsole trotzdem mit „Missing/invalid param.json" abbrechen – und der Dump sieht dabei einwandfrei aus.

---

## Was vorher durchrutschte

Fünf Fälle, alle syntaktisch gültig, alle für die Konsole unbrauchbar:

| Befund | Warum es bricht |
| --- | --- |
| `"contentVersion": 1.0` statt `"01.000.000"` | Als Zahl gespeichert geht die führende Null verloren |
| `contentId` nennt `PPSA99999`, `titleId` daneben `PPSA12345` | Die eingebettete Title-ID muss mit dem Feld übereinstimmen |
| `"applicationDrmType": "upgradable"` | Ein Anwendungstyp, kein DRM-Wert – gültig sind nur `standard`, `free`, `freemium` |
| `defaultLanguage` zeigt auf einen Sprachblock, den es nicht gibt | Die Konsole findet keinen Anzeigenamen |
| UTF-8-BOM am Dateianfang | Genügt allein für „invalid param.json"; jeder Texteditor zeigt die Datei trotzdem sauber an |

---

## Prüfen statt nur Lesen

Neu ist `ps5_validator/utils/param_check.py` mit drei Schweregraden, weil nicht jeder Verstoß gleich wiegt:

- **Fehler** – bricht auf der Konsole.
- **Warnung** – fällt auf, muss aber nicht scheitern.
- **Hinweis** – auffällig, vermutlich in Ordnung. `attribute`-Werte etwa sind Bitfelder; ungewohnte Kombinationen sind dort normal.

Die Pflichtfelder sind **zweistufig**, und das ist gemessen, nicht geraten: Die Beispieldatei des `ps5-payload-sdk` kommt mit drei Feldern aus und läuft auf der Konsole; ein Retail-Backup trägt den vollen Satz. Wer die volle Liste als Pflicht erklärt, meldet jedes Homebrew fälschlich als kaputt. Harte Pflicht sind deshalb nur `titleId`, `applicationCategoryType` und `localizedParameters`.

### Woher die Wertelisten stammen

Aus den Referenzwerkzeugen, nicht aus dem Bauch:

| Quelle | liefert |
| --- | --- |
| `LibProsperoPKG-2.5`, `ProsperoParamEnums.cs` | Schlüsselnamen, 30 Sprach- und 70 Ländercodes |
| `LibProsperoPKG-2.5`, `ProsperoApplicationType.cs` | die drei gültigen `applicationDrmType`-Tokens |
| `src/HomebrewTest/sce_sys/param.json` | eine vollständige, gültige Datei als Vorlage für die Reparatur |
| `ps5-payload-sdk`, `samples/install_app/FAKE02932` | das Gegenbeispiel: drei Felder, läuft trotzdem |

Dabei kam eine Verwechslung ans Licht, die weit verbreitet ist: **`upgradable` und `demo` sind keine `applicationDrmType`-Werte.** Es sind Anwendungstypen; `ProsperoApplicationTypes` bildet sie auf `standard` bzw. `free` ab. Die Prüfung sagt das jetzt beim Namen, statt nur „unbekannter Wert" zu melden – und die Reparatur zieht den Eintrag gerade.

---

## Reparieren statt ersetzen

Das ist der eigentliche Unterschied zum bisherigen Verhalten. Bisher gab es nur ein Angebot: eine neue `param.json` schreiben. Das warf weg, was noch stimmte – Titel, Altersfreigaben, Versionsstände.

Jetzt wird unterschieden:

| Lage | Angebot |
| --- | --- |
| Datei fehlt oder ist unlesbar (kein UTF-8, kaputtes JSON, UTF-16) | neu anlegen – wie bisher |
| Datei lesbar, aber beanstandet | **reparieren** – nur das Beanstandete wird berichtigt |

Repariert werden Versionen im falschen Typ, eine `contentId` mit abweichender Title-ID (die 16-stellige Kennung am Ende bleibt erhalten), der Anwendungstyp im DRM-Feld, fehlende Sprachblöcke, ein fehlender `ageLevel.default` und kaputte Hex-Felder. Fehlende Standardfelder werden mit den Werten der Referenzdatei aufgefüllt.

Vor dem Schreiben landet die bisherige Fassung als **`param.json.alt`** daneben. Der Eingriff geht in den Quellordner, nicht in eine Kopie – wer das Ergebnis nicht mag, hat den Ausgangszustand noch.

Danach läuft die Prüfung erneut. Bleibt ein Fehler stehen, ist die Datei so kaputt, dass nur eine neue hilft; dann greift der bisherige Weg.

---

## Auch im Validator

Aufgabe 8 prüfte die `param.json` bisher nur auf Existenz. Jetzt wird sie inhaltlich mitgeprüft, die Fehler stehen im Ergebnis, und die Reparatur wird gleich angeboten.

Anders als beim Bau bricht dort nichts ab: Der Validator soll berichten, nicht verhindern. Lehnt man ab, bleibt das Ergebnis stehen und der Befund im Protokoll.

---

## Drei Bauwege, eine Prüfung

Vor diesem Release stand derselbe Block dreimal wortgleich im Quelltext – bei `.ffpfsc`/`.ffpfs`, bei `.exfat` und bei `.ffpkg`. Jetzt rufen alle drei `_ensure_param_json()` auf. Ein Test hält fest, dass das alte `json.loads(param_json_path...)` nirgends zurückkehrt.

---

## Zwei Schalter für Skripte

Beim Nachsehen fiel ein Nebeneffekt auf: Im Kommandozeilenmodus ersetzt das Programm `messagebox.askyesno` durch eine Funktion, die stets `--yes` zurückgibt. Damit hätte `--yes` auch den Online-Nachschlag bejaht – und dabei geht die Title-ID an einen fremden Dienst. Ein Schalter, der Rückfragen zum Überschreiben abnickt, sollte das nicht nebenbei mitentscheiden.

| Schalter | Wirkung |
| --- | --- |
| `--param-json-reparieren` | repariert bzw. legt neu an, ohne Rückfrage |
| `--param-json-online` | erlaubt das Nachschlagen von Titel und Content-ID |

Beide sind aus, solange sie nicht gesetzt werden – auch mit `--yes`.

---

## Tests

**46 neue Prüfungen in `test_param_check.py`.** Zwei davon halten die Referenzdateien selbst gegen den Prüfer: Die vollständige aus LibProsperoPKG muss fehlerfrei durchgehen, die knappe aus dem `ps5-payload-sdk` ohne Fehler. Wäre die Prüfung zu streng, fiele die zweite durch; wäre sie zu lasch, fiele der Rest der Testreihe durch.

Dazu unverändert grün: `test_param_json_recovery` (18), `test_param_manifest` (5), `test_incomplete_dump` (8), `test_kleine_fixes` (28) sowie die vollständige Quality Suite.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `ps5_validator/utils/param_check.py` | **neu** – Prüfung und Reparatur |
| `test_param_check.py` | **neu** – 46 Prüfungen |
| `dist\PS5_Dump_Image_Converter_v1.8.51.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.51_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.8.51.sha256` | Prüfsummen aller Quelldateien |
