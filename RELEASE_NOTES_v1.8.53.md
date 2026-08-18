# PS5 Dump & Image Converter v1.8.53 – Release Notes

## Zweck dieses Releases

Eine fehlende `param.json` entsteht jetzt zum größten Teil aus dem Backup selbst — mit **einer** Rückfrage statt dreier. Und die selbst erzeugte Datei besteht endlich die eigene Prüfung.

---

## Der Fehler, der seit v1.8.51 drinsteckte

Mit v1.8.51 kam die inhaltliche Prüfung der `param.json`. Was dabei unterging: `create_default_param` stammt aus v1.8.35 und schrieb vier Felder. Solange niemand den Inhalt prüfte, fiel das nicht auf — seither meldete ausgerechnet die selbst erzeugte Datei Fehler:

```json
{"titleId": "PPSA06328", "applicationDrmType": "standard",
 "masterVersion": "01.00", "contentVersion": "01.00"}
```

| Befund | warum |
| --- | --- |
| `applicationCategoryType` fehlte | ohne dieses Feld erkennt die Konsole gar keinen Titel |
| `localizedParameters` fehlte | sobald kein Anzeigename bekannt war |
| `contentVersion` = `"01.00"` | das ist das Format von `masterVersion`; die Inhaltsversion braucht `01.000.000` |

Die Erstellung liefert jetzt ein Dokument, das die Prüfung besteht — und holt sich die Feldwerte aus `param_check.neu_anlegen`, damit es für „wie sieht eine gültige param.json aus" nur eine Stelle im Programm gibt.

---

## Drei neue lokale Quellen

Bisher kannte das Programm zwei Wege: `sce_sys/nptitle.dat` für die Titel-ID, alles Weitere über einen Online-Nachschlag. Eine Durchsuchung aller 1166 Dateien eines echten Backups ("Arkanoid Eternal Battle") hat drei weitere Fundstellen ergeben:

| Quelle | Feld | Befund |
| --- | --- | --- |
| `eboot.bin` | `titleId` | steht dort **genau einmal**, als `PPSA06328_00` — identisch mit `nptitle.dat` |
| `sce_sys/trophy2/trophy00.ucp` | `titleName` | `"titleMetadata":{"name":"Arkanoid - Eternal Battle"}` als lesbares JSON im Container |
| `sce_sys/pfs-version.dat` | `contentVersion` | zehn Byte Text, `01.002.000` |

**Die Inhaltsversion ist der wichtigste Zugewinn.** Bisher wurde beim Neuanlegen pauschal `01.000.000` eingetragen. Das Beispielbackup ist aber gepatcht — richtig ist `01.002.000`. Diese Angabe kann kein Online-Nachschlag liefern: Die Webseite kennt den aktuellen Ladenstand, nicht den Stand *dieses* Backups. Deshalb haben die lokalen Angaben Vorrang.

Zwei Messwerte zur Umsetzung:

- Die Titel-ID in der `eboot.bin` (26 MB) wird blockweise mit Überlappung gesucht — 0,17 s, und die Kennung kann nicht zwischen zwei Blöcken zerrissen werden.
- Der Titel im Trophäen-Container (7,8 MB) wird **von hinten** gesucht, weil der Metadatenblock 7,78 MB tief liegt. Das dauert 0,00 s statt eines Durchlaufs durch die ganze Datei.

### Was sich dort *nicht* holen lässt

- **Die Content-ID** steht in keiner Datei des Dumps — sie bleibt dem Online-Nachschlag vorbehalten.
- **Der Titel aus der `eboot.bin`**: Die Treffer auf den Spielnamen sind Klassenbezeichner aus dem Programmcode (`ArkanoidBallMoveSystem`), kein Anzeigename.
- **`param.sfo`**: das PS4-Format. PS5-Titel führen stattdessen die `param.json`; im untersuchten Backup gibt es keine.
- Ohne Fund blieben außerdem `ext_info.dat` (ein Flagfeld aus Nullen), `keystone`, die `uds`-Statistikdefinitionen und die 1150 Dateien in `PS5/`, `resources/` und `sce_module/`.

---

## Eine Bestätigung statt dreier

Die zweite Rückfrage — „Titel online nachschlagen?" — entfällt. Der Nachschlag läuft unmittelbar mit; dass dabei die Titel-ID an prosperopatches.com geht, steht jetzt in der einen Frage, die vorher kommt:

> Für dieses Spiel fehlt die Datei sce_sys/param.json. Soll automatisch eine param.json dafür erstellt werden?
>
> Titel-ID aus sce_sys/nptitle.dat gelesen: PPSA06328
>
> Titel und Content-ID stehen in keiner Datei des Backups. Sie werden zur Titel-ID PPSA06328 bei prosperopatches.com nachgeschlagen – dabei geht PPSA06328 dorthin, sonst nichts.

Im **Kommandozeilenmodus** bleibt es bei `--param-json-online`: Dort hat niemand diese Frage gesehen, und ein Skriptlauf soll nicht unbemerkt eine Kennung nach außen geben.

---

## An einem echten Backup vorgeführt

Die vorhandene, mit der alten Fassung erzeugte Datei wurde repariert:

```text
VORHER : 2 Fehler   (applicationCategoryType fehlt, contentVersion "01.00")
NACHHER: in Ordnung, 12 Felder statt 6
```

Sieben Änderungen, davon die aufschlussreichste: `contentVersion` von `01.00` auf **`01.002.000`** — aus `pfs-version.dat`. Erhalten blieb alles, was stimmte: Titel-ID, Content-ID und Anzeigename. Die alte Fassung liegt als `param.json.alt` daneben.

---

## Tests

95 Prüfungen in den vier berührten Dateien: `test_param_check` (46), `test_param_manifest` (5), `test_kleine_fixes` (36), `test_incomplete_dump` (8). Dazu die Release-Suite.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.53.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.53_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.8.53.sha256` | Prüfsummen aller Quelldateien |
